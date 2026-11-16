# pyright: reportMissingImports=false
import fitz  # PyMuPDF
import cv2
import numpy as np


def pdf_to_cv2_img(
    pdf_path,
    detail_level,
    page_num=0,
):

    doc = fitz.open(pdf_path)
    page = doc[page_num]
    pix = page.get_pixmap(matrix=fitz.Matrix(detail_level, detail_level))
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


def extract_pdf_slides(input_path, begin_page, end_page, output_path):
    for page_num in range(begin_page, end_page + 1):
        with fitz.open(input_path) as src:
            new_doc = fitz.open()
            new_doc.insert_pdf(src, from_page=page_num, to_page=page_num)
            path = f"{output_path}_{page_num}.pdf"
            new_doc.save(path)
        print(f"Success: Page {page_num} extracted -> {path}")


def crop_pdf(input_path, output_path, detail_level=3, page_num=0):
    img = pdf_to_cv2_img(input_path, detail_level, page_num)
    height, width = img.shape[:2]

    print("\n--- CROP PDF ---")
    print("W/A/S/D: Move selection | H/L: Width | K/J: Height")
    print("+/-: Change step | O: Toggle border")
    print("ENTER/E: Save crop | Q/ESC: Cancel")

    try:
        cropped, params, _, _ = select_patch_area(
            img,
            "CROP_DOC",
            [width, height, 0, 0, 20],
        )

        if cropped is None:
            return

        w, h, x, y, _ = params

        with fitz.open(input_path) as src, fitz.open() as result:
            source_page = src[page_num]

            source_page.remove_rotation()

            # Convert preview pixels into PDF coordinates.
            clip = (
                fitz.Rect(
                    x / detail_level,
                    y / detail_level,
                    (x + w) / detail_level,
                    (y + h) / detail_level,
                )
                & source_page.rect
            )

            page = result.new_page(
                width=clip.width,
                height=clip.height,
            )

            page.show_pdf_page(
                page.rect,
                src,
                page_num,
                clip=clip,
                keep_proportion=False,
            )

            pdf_bytes = result.tobytes(garbage=4, deflate=True)

        # Writing after closing the input also permits identical paths.
        with open(output_path, "wb") as output:
            output.write(pdf_bytes)

        print(f"Success: Cropped page saved -> {output_path}")

    finally:
        cv2.destroyAllWindows()


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


def master_patch_tool(target_pdf, source_pdf, output_path, detail_level=3):
    if detail_level <= 0:
        raise ValueError("detail_level must be positive")

    target_img = pdf_to_cv2_img(target_pdf, detail_level)
    source_img = pdf_to_cv2_img(source_pdf, detail_level)
    final_canvas = target_img.copy()

    target_height, target_width = target_img.shape[:2]
    source_height, source_width = source_img.shape[:2]

    patch_count = 0

    def pdf_rect(x, y, w, h, page):
        return (
            fitz.Rect(
                x / detail_level,
                y / detail_level,
                (x + w) / detail_level,
                (y + h) / detail_level,
            )
            & page.rect
        )

    print("\n--- PDF PATCH TOOL ---")
    print("Phase 1: Select target region, then ENTER.")
    print("Phase 2: Adjust source region, then ENTER to apply.")
    print("W/A/S/D: Move | H/L: Width | K/J: Height")
    print("+/-: Change step | O: Toggle border")
    print("Q/ESC: Finish and save confirmed patches.")

    try:
        with (
            fitz.open(target_pdf) as target_doc,
            fitz.open(source_pdf) as source_doc,
            fitz.open() as result,
        ):
            target_page = target_doc[0]
            source_page = source_doc[0]

            target_page.remove_rotation()
            source_page.remove_rotation()

            page = result.new_page(
                width=target_page.rect.width,
                height=target_page.rect.height,
            )
            page.show_pdf_page(
                page.rect,
                target_doc,
                0,
                keep_proportion=False,
            )

            finished = False

            while not finished:
                # PHASE 1: Select the destination on the target PDF.
                print(f"\nPatch {patch_count + 1}: select target region.")

                target_params = [
                    min(150, target_width),
                    min(150, target_height),
                    0,
                    0,
                    5,
                ]

                selection, target_params, _, _ = select_patch_area(
                    final_canvas,
                    "TARGET_DOC",
                    target_params,
                )

                if selection is None:
                    break

                cv2.destroyWindow("Preview: TARGET_DOC")

                tw, th, tx, ty, step = target_params

                # PHASE 2: Start with the same region in the source PDF.
                # Clamp only if the source page has different dimensions.
                sw = min(tw, source_width)
                sh = min(th, source_height)
                sx = max(0, min(tx, source_width - sw))
                sy = max(0, min(ty, source_height - sh))

                min_sw = min(10, source_width)
                min_sh = min(10, source_height)
                show_border = True

                print("Adjust source region; ENTER applies the patch.")

                while True:
                    sw = max(min_sw, min(sw, source_width))
                    sh = max(min_sh, min(sh, source_height))
                    sx = max(0, min(sx, source_width - sw))
                    sy = max(0, min(sy, source_height - sh))

                    source_patch = source_img[
                        sy : sy + sh,
                        sx : sx + sw,
                    ]
                    resized_patch = cv2.resize(source_patch, (tw, th))

                    # Show exactly where the patch will appear on the target.
                    preview = final_canvas.copy()
                    preview[ty : ty + th, tx : tx + tw] = resized_patch

                    if show_border:
                        cv2.rectangle(
                            preview,
                            (tx, ty),
                            (tx + tw - 1, ty + th - 1),
                            (255, 0, 0),
                            1,
                        )

                    cv2.imshow("TARGET_DOC", preview)

                    key = cv2.waitKey(0) & 0xFF

                    if key == ord("w"):
                        sy -= step
                    elif key == ord("s"):
                        sy += step
                    elif key == ord("a"):
                        sx -= step
                    elif key == ord("d"):
                        sx += step

                    elif key == ord("l"):
                        sw += step
                    elif key == ord("h"):
                        sw -= step
                    elif key == ord("j"):
                        sh += step
                    elif key == ord("k"):
                        sh -= step

                    elif key in [ord("+"), ord("=")]:
                        step = min(step + 5, 100)
                        print(f"Step: {step}")
                    elif key == ord("-"):
                        step = max(step - 5, 1)
                        print(f"Step: {step}")

                    elif key == ord("o"):
                        show_border = not show_border

                    elif key in [13, 10]:
                        target_rect = pdf_rect(tx, ty, tw, th, page)
                        source_rect = pdf_rect(sx, sy, sw, sh, source_page)

                        # Cover the destination before placing the source,
                        # matching the white-backed raster preview.
                        page.draw_rect(
                            target_rect,
                            color=None,
                            fill=(1, 1, 1),
                            overlay=True,
                        )

                        # Export original PDF content, not preview pixels.
                        page.show_pdf_page(
                            target_rect,
                            source_doc,
                            0,
                            clip=source_rect,
                            keep_proportion=False,
                            overlay=True,
                        )

                        final_canvas[
                            ty : ty + th,
                            tx : tx + tw,
                        ] = resized_patch

                        patch_count += 1
                        print(f"Patch {patch_count} applied.")
                        break

                    elif key in [ord("q"), 27]:
                        finished = True
                        break

            pdf_bytes = result.tobytes(garbage=4, deflate=True)

        # Close inputs before writing, permitting identical input/output paths.
        with open(output_path, "wb") as output:
            output.write(pdf_bytes)

        print(f"Success: {patch_count} patches saved -> {output_path}")

    finally:
        cv2.destroyAllWindows()


if __name__ == "__main__":
    extract_pdf_slides(
        "input/Skript Mathematik 3 WS 2026-27 Teil1 (Lineare Algebra).pdf",
        17,
        18,
        "dingus.pdf",
    )
    merge_pdfs(["dingus.pdf_17.pdf", "dingus.pdf_18.pdf"], "dingus.pdf")
    # crop_pdf("input/page_2.pdf", "output/page_2.pdf")
    #
    # merge_pdfs(
    #     [
    #         "output/slide_0.pdf",
    #         "input/slide_1.pdf",
    #         "input/slide_2.pdf",
    #         "input/slide_3.pdf",
    #         "input/slide_4.pdf",
    #         "output/slide_5.pdf",
    #         "output/page_1.pdf",
    #         "output/page_2.pdf",
    #         "input/slide_6.pdf",
    #         "input/slide_7.pdf",
    #         "input/slide_8.pdf",
    #         "output/slide_9.pdf",
    #         "output/page_3.pdf",
    #         "output/page_4.pdf",
    #     ],
    #     "output/combined.pdf",
    # )
