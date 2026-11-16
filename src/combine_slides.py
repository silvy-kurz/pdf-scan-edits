# pyright: reportMissingImports=false
import sys
import fitz
import cv2
import numpy as np

from pdf_manipulation import pdf_to_cv2_img, select_patch_area


def compare_regions(
    first_region,
    second_region,
    pixel_tolerance=10,
):
    """
    Return the percentage of pixels that changed between
    two equally-sized image regions.

    A pixel is considered changed if any of its three
    colour channels differs by more than pixel_tolerance.
    """

    first = first_region.astype(np.int16)
    second = second_region.astype(np.int16)

    difference = np.abs(first - second)

    changed_pixels = np.any(
        difference > pixel_tolerance,
        axis=2,
    )

    return np.mean(changed_pixels) * 100


def select_slide_number_region(
    pdf_path,
    initial_params=[20, 20, 1292, 739, 10],
    detail_level=3,
):
    """
    Show the first PDF page and use the existing patch
    selection tool to select the region containing the
    slide number.

    Returns:
        [width, height, x, y, step]
    """

    image = pdf_to_cv2_img(
        pdf_path,
        detail_level,
        page_num=0,
    )

    print()
    print("--- SELECT SLIDE NUMBER REGION ---")
    print()
    print("[W/A/S/D] Move")
    print("[L/H]     Change width")
    print("[J/K]     Change height")
    print("[+/-]     Change step")
    print("[O]       Toggle border")
    print("[ENTER]   Confirm")
    print("[Q]       Cancel")
    print()

    initial_params = [20, 20, 1292, 739, 10]

    _, params, key, _ = select_patch_area(
        image,
        "SLIDE NUMBER",
        initial_params,
    )

    cv2.destroyAllWindows()

    if key in [ord("q"), 27]:
        return None

    return params


def get_slide_number_regions(
    pdf_path,
    region_params,
    detail_level=3,
):
    """
    Render every page and extract the selected slide-number
    region.
    """

    width, height, x, y, _ = region_params

    with fitz.open(pdf_path) as doc:
        page_count = len(doc)

    regions = []

    for page_num in range(page_count):
        image = pdf_to_cv2_img(
            pdf_path,
            detail_level,
            page_num=page_num,
        )

        region = image[
            y : y + height,
            x : x + width,
        ]

        regions.append(region.copy())

        print(
            f"Rendered page {page_num + 1}/{page_count}",
            end="\r",
        )

    print()

    return regions


def detect_slide_groups(
    regions,
    pixel_tolerance=10,
    change_threshold=5.0,
):
    """
    Group consecutive PDF pages according to whether the
    selected slide-number region changed.

    Returns a list of lists containing zero-based page
    numbers.

    Example:

        [
            [0, 1, 2, 3],
            [4, 5, 6, 7],
            [8, 9, 10, 11],
        ]
    """

    if not regions:
        return []

    groups = []
    current_group = [0]

    for page_num in range(1, len(regions)):
        changed_percentage = compare_regions(
            regions[page_num - 1],
            regions[page_num],
            pixel_tolerance,
        )

        new_slide = changed_percentage >= change_threshold

        print(
            f"Pages {page_num} -> {page_num + 1}: "
            f"{changed_percentage:.2f}% changed"
            + ("  NEW SLIDE" if new_slide else "  same slide")
        )

        if new_slide:
            groups.append(current_group)
            current_group = [page_num]
        else:
            current_group.append(page_num)

    groups.append(current_group)

    return groups


def create_combined_pdf(
    input_pdf,
    output_pdf,
    slide_groups,
):
    """
    Create a PDF containing only the final page from each
    detected slide group.
    """

    source = fitz.open(input_pdf)
    output = fitz.open()

    for group in slide_groups:
        final_page = group[-1]

        output.insert_pdf(
            source,
            from_page=final_page,
            to_page=final_page,
        )

    output.save(output_pdf)

    output.close()
    source.close()


def combine_revealed_slides(
    input_pdf,
    output_pdf,
    detail_level=3,
    pixel_tolerance=10,
    change_threshold=5.0,
):
    """
    Complete process:

        1. Select slide-number region.
        2. Extract that region from every page.
        3. Compare consecutive regions.
        4. Detect actual slide groups.
        5. Keep the final page of every group.
        6. Write those pages to a new PDF.
    """

    region_params = select_slide_number_region(
        input_pdf,
        detail_level,
    )

    if region_params is None:
        print("Cancelled.")
        return

    print()
    print("Selected region:")
    print(
        f"width={region_params[0]}, "
        f"height={region_params[1]}, "
        f"x={region_params[2]}, "
        f"y={region_params[3]}"
    )
    print()

    regions = get_slide_number_regions(
        input_pdf,
        region_params,
        detail_level,
    )

    slide_groups = detect_slide_groups(
        regions,
        pixel_tolerance,
        change_threshold,
    )

    print()
    print("--- DETECTED SLIDES ---")

    for slide_number, group in enumerate(
        slide_groups,
        start=1,
    ):
        print(f"Slide {slide_number}: pages {group[0] + 1}-{group[-1] + 1}")

    print()

    create_combined_pdf(
        input_pdf,
        output_pdf,
        slide_groups,
    )

    print(f"Success: {len(slide_groups)} slides written to {output_pdf}")


def main(argv, argc):
    print(argc)
    combine_revealed_slides(argv[1], argv[2])


if __name__ == "__main__":
    main(sys.argv, len(sys.argv))
