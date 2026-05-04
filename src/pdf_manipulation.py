import fitz  # PyMuPDF
import cv2
import numpy as np
import os


class PDFEditor:
    def __init__(self):
        pass

    # --- TASK 1: MERGE & SPLIT ---
    def merge_pdfs(self, input_paths, output_path):
        """Combines a list of PDF paths into one file."""
        result = fitz.open()
        for path in input_paths:
            with fitz.open(path) as m:
                result.insert_pdf(m)
        result.save(output_path)
        print(f"Merged {len(input_paths)} files into {output_path}")

    def extract_page(self, input_path, page_num, output_path):
        """Splits a single page out of a PDF."""
        with fitz.open(input_path) as src:
            new_doc = fitz.open()
            new_doc.insert_pdf(src, from_page=page_num, to_page=page_num)
            new_doc.save(output_path)
        print(f"Extracted page {page_num} to {output_path}")

    # --- TASK 2: CROP ---
    def crop_page(self, input_path, output_path, crop_rect):
        """
        crop_rect: (x0, y0, x1, y1) coordinates.
        Note: PDFs use a coordinate system usually starting at top-left.
        """
        doc = fitz.open(input_path)
        for page in doc:
            page.set_cropbox(fitz.Rect(crop_rect))
        doc.save(output_path)
        print(f"Cropped PDF saved to {output_path}")

    # --- TASK 3: INTERACTIVE STAMPING (FIXED) ---
    def interactive_stamp(self, target_pdf, source_pdf, output_path, source_crop):
        """
        target_pdf: Die Hausaufgabe, die korrigiert werden soll.
        source_pdf: Die PDF, die den 'guten' Patch oder das leere Papier enthält.
        source_crop: (x0, y0, x1, y1) des Bereichs in der Quell-PDF.
        """
        # 1. Patch aus der Quell-PDF extrahieren (als Bild im Speicher)
        src_doc = fitz.open(source_pdf)
        src_page = src_doc[0]
        # Erstellt ein Bild vom spezifischen Bereich (Crop)
        pix_patch = src_page.get_pixmap(
            clip=fitz.Rect(source_crop), matrix=fitz.Matrix(2, 2)
        )
        img_patch = np.frombuffer(pix_patch.samples, dtype=np.uint8).reshape(
            pix_patch.h, pix_patch.w, 3
        )
        img_patch = cv2.cvtColor(img_patch, cv2.COLOR_RGB2BGR)

        # Zwischenspeichern als temporäres PNG für PyMuPDF insert_image
        temp_patch_path = "temp_patch.png"
        cv2.imwrite(temp_patch_path, img_patch)

        # 2. Ziel-PDF für OpenCV vorbereiten
        doc = fitz.open(target_pdf)
        page = doc[0]
        pix_target = page.get_pixmap(matrix=fitz.Matrix(2, 2))
        img_target = np.frombuffer(pix_target.samples, dtype=np.uint8).reshape(
            pix_target.h, pix_target.w, 3
        )
        img_target = cv2.cvtColor(img_target, cv2.COLOR_RGB2BGR)

        sh, sw = img_patch.shape[:2]
        display_img = img_target.copy()
        stamps_to_apply = []

        def mouse_callback(event, x, y, flags, param):
            nonlocal display_img
            if event == cv2.EVENT_LBUTTONDOWN:
                # Koordinaten speichern (skaliert auf PDF-Punkte)
                stamps_to_apply.append((x / 2, y / 2))
                # Vorschau im Fenster (Rechteck zeichnen)
                cv2.rectangle(display_img, (x, y), (x + sw, y + sh), (255, 0, 0), 2)
                cv2.imshow("Klick zum Stempeln - 'S' zum Speichern", display_img)

        cv2.imshow("Klick zum Stempeln - 'S' zum Speichern", display_img)
        cv2.setMouseCallback("Klick zum Stempeln - 'S' zum Speichern", mouse_callback)

        while True:
            key = cv2.waitKey(1) & 0xFF
            if key == ord("s"):
                break
            if key == 27:
                return

        # 3. Den Patch an allen geklickten Stellen in die PDF 'einbrennen'
        for sx, sy in stamps_to_apply:
            # Wir berechnen die Zielbox basierend auf der Originalgröße des Patches
            # source_crop[2]-source_crop[0] gibt die Breite in PDF-Punkten
            patch_w = source_crop[2] - source_crop[0]
            patch_h = source_crop[3] - source_crop[1]
            rect = fitz.Rect(sx, sy, sx + patch_w, sy + patch_h)
            page.insert_image(rect, filename=temp_patch_path)

        doc.save(output_path)
        src_doc.close()
        if os.path.exists(temp_patch_path):
            os.remove(temp_patch_path)
        cv2.destroyAllWindows()
        print(f"Reparierte PDF unter {output_path} gespeichert.")


# --- EXAMPLE USAGE ---
if __name__ == "__main__":
    editor = PDFEditor()

    # Task 1: Merge
    editor.merge_pdfs(["scan1.pdf", "scan2.pdf"], "combined.pdf")

    # Task 2: Crop (x0, y0, x1, y1)
    editor.crop_page("combined.pdf", "cropped.pdf", (50, 50, 400, 400))

    # Task 3: Interactive Stamp
    # Beispiel: Nehme aus 'patch.pdf' ein Rechteck von (100, 100) bis (200, 150)
    # und stempel es in 'homework.pdf'
    editor.interactive_stamp(
        "homework.pdf",
        "patch.pdf",
        "fixed_homework.pdf",
        source_crop=(100, 100, 200, 150),
    )

    print("Uncomment the lines in __main__ to run specific tasks.")
