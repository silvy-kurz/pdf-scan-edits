# pyright: reportMissingImports=false
import os
import json
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from shutil import copyfileobj
import shutil
from tempfile import NamedTemporaryFile
from uuid_extensions import uuid7str
import subprocess

ID_META_TAG = "XMP-xmpMM:DocumentID"


def get_metadata_id(path: Path) -> str | None:
    result = subprocess.run(
        ["exiftool", "-j", "-G1", f"-{ID_META_TAG}", str(path)],
        check=True,
        capture_output=True,
        encoding="utf-8",
    )

    metadata = json.loads(result.stdout)[0]
    value = metadata.get(ID_META_TAG)
    return str(value) if value is not None and value != "" else None


def delete_metadata_id(path: Path):
    path = Path(path).resolve(strict=True)

    subprocess.run(
        ["exiftool", "-overwrite_original", f"-{ID_META_TAG}=", str(path)],
        check=True,
        capture_output=True,
        encoding="utf-8",
    )

    if get_metadata_id(path) is not None:
        raise RuntimeError(f"Document ID was not cleared from {path}")


def write_metadata_id(path: Path, document_id: str):
    if not document_id.strip():
        raise ValueError("Document ID must not be empty")

    path = Path(path).resolve(strict=True)
    subprocess.run(
        ["exiftool", "-overwrite_original", f"-{ID_META_TAG}={document_id}", str(path)],
        check=True,
        capture_output=True,
        encoding="utf-8",
    )

    if get_metadata_id(path) != document_id:
        raise RuntimeError(f"Document ID was not written to {path}")


DEFAULT_HISTORY = {"Tracks": []}
SNAPSHOT_FOLDER_NAME = "SNAPSHOTS"
HISTORY_FILE_NAME = "history.json"


def check_item_exists(path, is_file, raise_error=True):
    if is_file:
        if not path.is_file():
            if raise_error:
                raise FileNotFoundError(f"File Missing: {path}")
            else:
                return False

    else:
        if not path.is_dir():
            if raise_error:
                raise FileNotFoundError(f"Folder Missing: {path}")
            else:
                return False

    return True


@dataclass
class Snapshot:
    command: str
    timestamp: str
    name: str

    @classmethod
    def create(cls, index, command=None):
        if command is None:
            command = "Created"

        return cls(command, str(datetime.now()), f"SN{index}")


@dataclass
class FileTrack:
    tracking_id: str
    path: Path
    created_timestamp: str
    snapshot_folder: Path
    snapshots: list[Snapshot]

    def to_dict(self):
        return {
            "tracking_id": self.tracking_id,
            "path": self.path.as_posix(),
            "created_timestamp": self.created_timestamp,
            "snapshot_folder": self.snapshot_folder.as_posix(),
            "snapshots": [asdict(snapshot) for snapshot in self.snapshots],
        }

    @classmethod
    def from_dict(cls, data):
        return cls(
            tracking_id=data["tracking_id"],
            path=Path(data["path"]),
            created_timestamp=data["created_timestamp"],
            snapshot_folder=Path(data["snapshot_folder"]),
            snapshots=[Snapshot(**item) for item in data["snapshots"]],
        )

    @property
    def snapshot_count(self) -> int:
        return len(self.snapshots)

    @classmethod
    def create(cls, tracking_id, path, snapshot_folder_path):
        snapshots_folder = snapshot_folder_path / tracking_id
        os.makedirs(snapshots_folder)
        return cls(tracking_id, path, str(datetime.now()), snapshots_folder, [])

    def write_snapshot_to_file(self, index, path):
        snapshot_path = self.snapshot_folder / self.snapshots[index].name

        with snapshot_path.open("rb") as source:
            with NamedTemporaryFile(mode="wb", dir=path.parent, delete=False) as temp:
                temp_path = Path(temp.name)
                try:
                    copyfileobj(source, temp)
                    temp.close()
                    temp_path.replace(path)

                finally:
                    temp_path.unlink(missing_ok=True)

    def track_snapshot(self, snapshot, file_bytes):
        snapshot_path = self.snapshot_folder / snapshot.name
        with snapshot_path.open("xb") as file:
            file.write(file_bytes)
        self.snapshots.append(snapshot)


class History:
    def __init__(self, root: Path, history_name=HISTORY_FILE_NAME):
        self.history_location = root / history_name
        with self.history_location.open("r", encoding="utf-8") as history_file:
            self.deserialise_history(history_file)

        check_item_exists(self.snapshot_folder_path, is_file=False)
        for track in self.tracks:
            check_item_exists(track.snapshot_folder, is_file=False)
            for snapshot in track.snapshots:
                check_item_exists(track.snapshot_folder / snapshot.name, is_file=True)

    def read_file_id(self, path):
        return get_metadata_id(path)

    def write_file_id(self, path, id):
        write_metadata_id(path, id)

    def deserialise_history(self, history_file):
        history = json.load(history_file)
        self.root = Path(history["root"])
        self.snapshot_folder_path = Path(history["snapshot_folder_path"])
        self.tracks = [FileTrack.from_dict(entry) for entry in history["tracks"]]

    def serialise_history(self):
        data = {
            "root": str(self.root),
            "snapshot_folder_path": str(self.snapshot_folder_path),
            "tracks": [track.to_dict() for track in self.tracks],
        }
        text = json.dumps(data, indent=4) + "\n"

        temp_path = None
        try:
            with NamedTemporaryFile(
                mode="w", encoding="utf-8", dir=self.root, delete=False
            ) as temp:
                temp_path = Path(temp.name)
                temp.write(text)

            temp_path.replace(self.history_location)
        finally:
            if temp_path is not None:
                temp_path.unlink(missing_ok=True)

    def reset_history(self):
        for track in self.tracks:
            delete_metadata_id(track.path)

        shutil.rmtree(self.root)
        os.makedirs(self.root)
        os.makedirs(self.snapshot_folder_path)
        self.tracks = []
        self.serialise_history()

    @property
    def tracked_file_ids(self):
        return [track.tracking_id for track in self.tracks]

    @classmethod
    def create(cls, root: str | Path, history_name=HISTORY_FILE_NAME, strict=True):
        print(f"Creating Tracker Folder At: {root}")

        if isinstance(root, str):
            root_path = Path(root).resolve()
        else:
            root_path = root
        if check_item_exists(root_path, is_file=False, raise_error=False):
            if strict:
                raise FileExistsError(
                    "Root Folder Already Exists (Set strict = False if Intentional)"
                )
        else:
            os.makedirs(root)

        snapshot_path = root_path / SNAPSHOT_FOLDER_NAME
        if check_item_exists(snapshot_path, is_file=False, raise_error=False):
            if strict:
                raise FileExistsError(
                    "Snapshot Folder Already Exists (Set strict = False if Intentional)"
                )
        else:
            os.makedirs(os.path.join(root, SNAPSHOT_FOLDER_NAME))

        history_location = root_path / history_name
        if check_item_exists(history_location, is_file=True, raise_error=False):
            if strict:
                raise FileExistsError(
                    "History File Already Exists (Set strict = False if Intentional)"
                )
        else:
            with open(history_location, "w") as history_file:
                initial_history = {
                    "root": root_path.as_posix(),
                    "snapshot_folder_path": snapshot_path.as_posix(),
                    "tracks": [],
                }
                history_str = json.dumps(initial_history, indent=4)
                history_file.write(history_str)

        return cls(root_path)

    def create_file_id(self):
        return f"{uuid7str()}_FH"

    def add_snapshot(self, path: Path, file_bytes=None, command=None):
        path = path.resolve()
        file_id = self.read_file_id(path)

        if file_id is not None and file_id in self.tracked_file_ids:
            if command is None:
                raise ValueError(
                    "Need to Specify Command for Snapshot for Already Tracked PDFS"
                )

            track = self.tracks[self.tracked_file_ids.index(file_id)]
            if path != track.path:
                print("Tracked Path Appears Out of Date, Applying Update: ")
                print(f"    {track.path} -> {path}")
                track.path = path
        else:
            track = FileTrack.create(
                self.create_file_id(), path, self.root / SNAPSHOT_FOLDER_NAME
            )
            self.write_file_id(path, track.tracking_id)
            self.tracks.append(track)

        if file_bytes is None:
            with path.open("rb") as source:
                track.track_snapshot(
                    Snapshot.create(track.snapshot_count, command), source.read()
                )

        else:
            track.track_snapshot(
                Snapshot.create(track.snapshot_count, command), file_bytes
            )
            snapshot_path = track.snapshot_folder / track.snapshots[-1].name
            self.write_file_id(snapshot_path, track.tracking_id)

        self.serialise_history()

    def load_snapshot_to_file(self, path, index):
        file_id = self.read_file_id(path)
        if file_id not in self.tracked_file_ids:
            raise ValueError("No Tracker for This File Found")
        track = self.tracks[self.tracked_file_ids.index(file_id)]
        if not 0 <= index < track.snapshot_count:
            raise ValueError("Requested Snapshot Does not Exist")

        track.write_snapshot_to_file(index, path)


UNI_HISTORY_PATH = Path.home() / "UNI/.UNIHIS"


def main():

    history = History(UNI_HISTORY_PATH)

    file_name = Path("input/patch.pdf")
    history.add_snapshot(file_name, command="Cropped")


if __name__ == "__main__":
    main()
