import fitz  # PyMuPDF
import cv2
import numpy as np

ZOOM = 2


def pdf_to_cv2_img(pdf_path, page_num=0):
    """Konvertiert eine PDF-Seite in ein OpenCV-kompatibles Bild."""
    doc = fitz.open(pdf_path)
    page = doc[page_num]
    pix = page.get_pixmap(matrix=fitz.Matrix(ZOOM, ZOOM))
    img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.h, pix.w, 3)
    img = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)
    doc.close()
    return img


def merge_pdfs(input_paths, output_path):
    result = fitz.open()
    for path in input_paths:
        with fitz.open(path) as m:
            result.insert_pdf(m)
    result.save(output_path)
    print(f"Erfolg: {len(input_paths)} Dateien zusammengeführt -> {output_path}")


def split_pdf(input_path, page_num, output_path):
    with fitz.open(input_path) as src:
        new_doc = fitz.open()
        new_doc.insert_pdf(src, from_page=page_num, to_page=page_num)
        new_doc.save(output_path)
    print(f"Erfolg: Seite {page_num} extrahiert -> {output_path}")


def crop_pdf(input_path, output_path, coords):
    """coords: (x0, y0, x1, y1) in PDF-Punkten"""
    doc = fitz.open(input_path)
    for page in doc:
        page.set_cropbox(fitz.Rect(coords))
    doc.save(output_path)
    doc.close()
    print(f"Erfolg: PDF zugeschnitten -> {output_path}")


def select_patch_area(image, title, params, overlay_img=None):
    """
    Erweiterte Version deiner Navigations-Logik.
    overlay_img: Wenn gesetzt, wird dieses Bild anstelle des Rahmens angezeigt.
    """
    w, h, x, y, step = params
    height, width, _ = image.shape

    while True:
        x = max(0, min(x, width - w))
        y = max(0, min(y, height - h))
        w = max(10, min(w, width - x))
        h = max(10, min(h, height - y))

        display_img = image.copy()

        if overlay_img is not None:
            resized_overlay = cv2.resize(overlay_img, (w, h))
            display_img[y : y + h, x : x + w] = resized_overlay
            cv2.rectangle(display_img, (x, y), (x + w, y + h), (255, 0, 0), 1)
        else:
            cv2.rectangle(display_img, (x, y), (x + w, y + h), (0, 255, 0), 2)

        subset = image[y : y + h, x : x + w]
        cv2.imshow(f"{title} - Main", display_img)
        cv2.imshow(f"{title} - Current Subset", subset)

        key = cv2.waitKey(0) & 0xFF

        if key == ord("w"):
            y -= step
        elif key == ord("s"):
            y += step
        elif key == ord("a"):
            x -= step
        elif key == ord("d"):
            x += step
        elif key == ord("l"):
            w += step
        elif key == ord("h"):
            w -= step
        elif key == ord("j"):
            h += step
        elif key == ord("k"):
            h -= step
        elif key == ord("+"):
            step = min(step + 5, 50)
        elif key == ord("-"):
            step = max(step - 5, 1)

        elif key in [ord("e"), 13, ord("q"), 27]:
            return subset, [w, h, x, y, step], key


def master_patch_tool(target_pdf, source_pdf, output_path):
    target_img = pdf_to_cv2_img(target_pdf)
    source_img = pdf_to_cv2_img(source_pdf)

    patches = []
    current_params = [150, 150, 50, 50, 20]

    print("\n--- PHASE 1: PATCHES AUS QUELLE WÄHLEN ---")
    print(
        "[ENTER]: Patch speichern & weiteren wählen | [E]: Fertig | [Q/ESC]: Abbrechen"
    )

    while True:
        subset, current_params, key = select_patch_area(
            source_img, "SOURCE", current_params
        )
        if key in [ord("q"), 27]:
            return

        patches.append(subset)
        if key == ord("e"):
            break

    print("\n--- PHASE 2: PATCHES IM ZIEL PLATZIEREN ---")
    final_placements = []

    for i, p_img in enumerate(patches):
        ph, pw, _ = p_img.shape
        place_params = [pw, ph, 100, 100, 10]

        _, final_params, key = select_patch_area(
            target_img,
            f"PLACEMENT {i + 1}/{len(patches)}",
            place_params,
            overlay_img=p_img,
        )

        if key in [ord("q"), 27]:
            return

        w, h, x, y, _ = final_params
        rect = fitz.Rect(x / ZOOM, y / ZOOM, (x + w) / ZOOM, (y + h) / ZOOM)
        final_placements.append((rect, p_img))

    doc = fitz.open(target_pdf)
    page = doc[0]
    for rect, img_data in final_placements:
        _, img_enc = cv2.imencode(".png", img_data)
        page.insert_image(rect, stream=img_enc.tobytes())

    doc.save(output_path)
    doc.close()
    cv2.destroyAllWindows()
    print(f"\nDatei erfolgreich gespeichert: {output_path}")


if __name__ == "__main__":
    # --- TEST 1: MERGE ---
    merge_pdfs(["input/scan1.pdf", "input/scan2.pdf"], "output/combined.pdf")

    # --- TEST 2: SPLIT ---
    split_pdf("output/combined.pdf", 0, "input/single_page.pdf")

    # --- TEST 3: CROP ---
    crop_pdf("input/scan1.pdf", "temps/cropped.pdf", (50, 50, 400, 600))

    # --- TEST 4: INTERACTIVE PATCHING ---
    master_patch_tool("homework.pdf", "temps/patch.pdf", "fixed.pdf")
