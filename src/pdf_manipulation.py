import fitz  # PyMuPDF
import cv2
import numpy as np

ZOOM = 3


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
    print(f"Success: {len(input_paths)} Pages combined into PDF -> {output_path}")


def split_pdf(input_path, page_num, output_path):
    with fitz.open(input_path) as src:
        new_doc = fitz.open()
        new_doc.insert_pdf(src, from_page=page_num, to_page=page_num)
        new_doc.save(output_path)
    print(f"Success: Page {page_num} extracted -> {output_path}")


def crop_pdf(input_path, output_path, subset_cord):
    img = pdf_to_cv2_img(input_path)

    h, w, _ = img.shape
    image_fullsize = (w, h, w, h)
    clamped_subset = tuple(
        [
            min(max(0, cord), fullcord)
            for cord, fullcord in zip(subset_cord, image_fullsize)
        ]
    )
    min_x, min_y, max_x, max_y = clamped_subset
    print(h, w)
    print(clamped_subset)
    cropped = img[min_y:max_y, min_x:max_x]

    success, img_bytes = cv2.imencode(".png", cropped)
    if not success:
        raise RuntimeError("Image encoding failed")

    doc = fitz.open()

    pdf_w = max_x / ZOOM
    pdf_h = max_y / ZOOM

    page = doc.new_page(width=pdf_w, height=pdf_h)

    page.insert_image(fitz.Rect(0, 0, pdf_w, pdf_h), stream=img_bytes.tobytes())

    doc.save(output_path)
    doc.close()


def select_patch_area(image, title, params, overlay_img=None, show_border=True):
    w, h, x, y, step = params
    height, width, _ = image.shape

    while True:
        x = max(0, min(x, width - w))
        y = max(0, min(y, height - h))
        w = max(10, min(w, width - x))
        h = max(10, min(h, height - y))

        display_img = image.copy()

        if overlay_img is not None:
            resized_ov = cv2.resize(overlay_img, (w, h))
            display_img[y : y + h, x : x + w] = resized_ov

        if show_border:
            color = (255, 0, 0) if overlay_img is not None else (255, 0, 0)
            cv2.rectangle(display_img, (x, y), (x + w, y + h), color, 1)

        subset = image[y : y + h, x : x + w]
        cv2.imshow(title, display_img)
        cv2.imshow(f"Preview: {title}", subset)

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

        elif key == ord("+") or key == ord("="):
            step = min(step + 5, 100)
            print(f"Step: {step}")
        elif key == ord("-"):
            step = max(step - 5, 1)
            print(f"Step: {step}")

        elif key == ord("o"):
            show_border = not show_border

        elif key in [ord("e"), 13]:
            return subset, [w, h, x, y, step], key, show_border
        elif key in [ord("q"), 27]:
            return None, [w, h, x, y, step], key, show_border


def master_patch_tool(target_pdf, source_pdf, output_path):
    target_img = pdf_to_cv2_img(target_pdf)
    source_img = pdf_to_cv2_img(source_pdf)

    final_canvas = target_img.copy()

    # PHASE 1
    print("\n--- PHASE 1: FEHLER IM ZIEL MARKIEREN ---")
    print(
        "[ENTER]: Fehler bestätigen | [E]: Fertig (weiter zu Phase 2) | [Q]: Abbrechen"
    )
    error_regions = []
    current_params = [150, 150, 50, 50, 20]

    while True:
        _, current_params, key, _ = select_patch_area(
            target_img, "TARGET_DOC", current_params
        )
        if key in [ord("q"), 27]:
            return
        error_regions.append(list(current_params))
        if key == ord("e"):
            break

    # PHASE 2
    print("\n--- PHASE 2: PATCHES AUSWÄHLEN (VORSCHAU IM TARGET_DOC) ---")
    print("[ENTER]: Patch einbrennen | [Q]: Abbrechen")

    for i, region in enumerate(error_regions):
        tw, th, tx, ty, _ = region

        sw, sh, sx, sy, s_step = tw, th, tx, ty, 5
        show_border = True

        while True:
            sx = max(0, min(sx, source_img.shape[1] - sw))
            sy = max(0, min(sy, source_img.shape[0] - sh))
            current_patch = source_img[sy : sy + sh, sx : sx + sw]

            preview_canvas = final_canvas.copy()
            resized_patch = cv2.resize(current_patch, (tw, th))
            preview_canvas[ty : ty + th, tx : tx + tw] = resized_patch

            if show_border:
                cv2.rectangle(
                    preview_canvas, (tx, ty), (tx + tw, ty + th), (255, 0, 0), 1
                )

            cv2.imshow("TARGET_DOC", preview_canvas)

            source_display = source_img.copy()
            cv2.rectangle(source_display, (sx, sy), (sx + sw, sy + sh), (0, 255, 0), 2)
            cv2.imshow(f"SOURCE_SELECT_{i + 1}", source_display)

            key = cv2.waitKey(0) & 0xFF
            if key == ord("w"):
                sy -= s_step
            elif key == ord("s"):
                sy += s_step
            elif key == ord("a"):
                sx -= s_step
            elif key == ord("d"):
                sx += s_step

            elif key == ord("l"):
                sw += s_step
            elif key == ord("h"):
                sw -= s_step
            elif key == ord("j"):
                sh += s_step
            elif key == ord("k"):
                sh -= s_step

            elif key == ord("o"):
                show_border = not show_border
            elif key in [ord("+"), ord("=")]:
                s_step = min(s_step + 5, 50)
            elif key == ord("-"):
                s_step = max(s_step - 5, 1)

            elif key in [ord("e"), 13]:
                final_canvas[ty : ty + th, tx : tx + tw] = resized_patch
                cv2.destroyWindow(f"SOURCE_SELECT_{i + 1}")
                break
            elif key in [ord("q"), 27]:
                return

    # --- PDF EXPORT ---
    doc_orig = fitz.open(target_pdf)
    rect_orig = doc_orig[0].rect
    new_doc = fitz.open()
    new_page = new_doc.new_page(width=rect_orig.width, height=rect_orig.height)

    _, img_enc = cv2.imencode(".png", final_canvas)
    new_page.insert_image(rect_orig, stream=img_enc.tobytes())

    new_doc.save(output_path)
    new_doc.close()
    doc_orig.close()
    cv2.destroyAllWindows()
    print(f"Succesful Patching PDF: {output_path}")


if __name__ == "__main__":
    # split_pdf("output/combined.pdf", 1, "input/single_page.pdf")
    #
    # master_patch_tool("input/page_4.pdf", "temps/patch.pdf", "temps/page_4.pdf")
    # master_patch_tool("input/page_5.pdf", "temps/patch.pdf", "temps/page_5.pdf")
    master_patch_tool("input/page_5.pdf", "temps/patch.pdf", "temps/test_page_5.pdf")
    # crop_pdf("temps/page_2.pdf", "temps/crp_page_2.pdf", (0, 0, 2000, 1100))
    #
    # merge_pdfs(
    #     [
    #         "input/page_1.pdf",
    #         "temps/crp_page_2.pdf",
    #         "input/page_3.pdf",
    #         "temps/page_4.pdf",
    #         "temps/page_5.pdf",
    #         "input/page_6.pdf",
    #     ],
    #     "output/combined.pdf",
    # )
