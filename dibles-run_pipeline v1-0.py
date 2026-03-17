import os
import re
import csv
import shutil
from pathlib import Path
from io import BytesIO

from PyPDF2 import PdfReader, PdfWriter, PdfMerger
from reportlab.pdfgen import canvas


# ----------------------------
# Configuration
# ----------------------------
DOWNLOADED_DIR = Path("downloaded_pdfs")
INPUT_DIR = Path("input_pdfs")
OUTPUT_DIR = Path("output_pdfs")
COMBINED_DIR = Path("combined_pdfs")

POWERSCHOOL_EXPORT = Path("student.export.text")  # fixed PowerSchool filename
ID_LIST_TXT = Path("id_list.txt")
FILE_LIST_CSV = Path("file_list.csv")  # optional audit output

BATCH_SIZE = 500  # adjust to what your platform accepts

# overlay text settings
OVERLAY_FONT = "Helvetica"
OVERLAY_FONT_SIZE = 10
OVERLAY_TEXT_PREFIX = "Student ID: "  # change to "Student Number: " if you prefer
OVERLAY_X = 450
OVERLAY_Y = 770


# ----------------------------
# Helpers
# ----------------------------
def pause(msg: str) -> None:
    print("\n" + msg)
    input("Press Enter to continue...")

def ensure_dirs() -> None:
    DOWNLOADED_DIR.mkdir(parents=True, exist_ok=True)
    INPUT_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    COMBINED_DIR.mkdir(parents=True, exist_ok=True)

def folder_is_empty(folder: Path) -> bool:
    return not any(p for p in folder.iterdir() if p.is_file() and p.suffix.lower() == ".pdf")


def refuse_if_not_empty() -> None:
    non_empty = []
    for d in [INPUT_DIR, OUTPUT_DIR, COMBINED_DIR]:
        if d.exists() and not folder_is_empty(d):
            non_empty.append(d)

    if non_empty:
        print("❌ Safety stop: these folders must be empty before running:")
        for d in non_empty:
            print(f"   - {d} (not empty)")
        print("\nMove/delete the contents of those folders, then rerun.")
        raise SystemExit(2)

def list_downloaded_pdfs() -> list[Path]:
    pdfs = sorted([p for p in DOWNLOADED_DIR.iterdir() if p.is_file() and p.suffix.lower() == ".pdf"])
    return pdfs

def extract_id_from_filename(pdf_path: Path) -> str | None:
    """
    Expected filename format: 123456.pdf
    Return '123456' if valid, else None.
    """
    stem = pdf_path.stem.strip()
    if re.fullmatch(r"\d+", stem):
        return stem
    return None

def write_id_lists(ids: list[str], pdf_names: list[str]) -> None:
    # ID list for PowerSchool copy/paste
    ID_LIST_TXT.write_text("\n".join(ids) + "\n", encoding="utf-8")

    # Optional audit file list (matches your earlier habit)
    with open(FILE_LIST_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["filename"])
        for name in pdf_names:
            w.writerow([name])

def read_powerschool_export() -> dict[str, str]:
    """
    Reads tab-delimited students.export.text with headers:
      id    student_number

    Returns mapping {id: student_number}
    """
    if not POWERSCHOOL_EXPORT.exists():
        print(f"❌ PowerSchool export not found: {POWERSCHOOL_EXPORT}")
        raise SystemExit(2)

    mapping: dict[str, str] = {}
    with open(POWERSCHOOL_EXPORT, "r", newline="", encoding="utf-8", errors="replace") as f:
        reader = csv.DictReader(f, delimiter="\t")
        if not reader.fieldnames:
            print("❌ PowerSchool export appears empty or unreadable.")
            raise SystemExit(2)

        headers = [h.strip().lower() for h in reader.fieldnames]
        if "id" not in headers or "student_number" not in headers:
            print("❌ PowerSchool export must include headers: id and student_number")
            print(f"   Found headers: {reader.fieldnames}")
            raise SystemExit(2)

        # map normalized -> actual key
        header_map = {h.strip().lower(): h for h in reader.fieldnames}
        id_key = header_map["id"]
        sn_key = header_map["student_number"]

        for row in reader:
            sid = (row.get(id_key) or "").strip()
            sn = (row.get(sn_key) or "").strip()

            if not sid or not sn:
                continue

            # normalize id (should be digits)
            sid = sid.strip()
            sn = sn.strip()

            mapping[sid] = sn

    return mapping

def rename_and_move(downloaded_pdfs: list[Path], id_to_student_number: dict[str, str]) -> None:
    """
    Moves:
      downloaded_pdfs/{id}.pdf -> input_pdfs/{student_number}.pdf

    Refuses on collisions or missing mapping.
    """
    # Validate mapping coverage + collisions
    downloaded_ids = []
    for p in downloaded_pdfs:
        sid = extract_id_from_filename(p)
        if sid is None:
            print(f"❌ Unexpected filename (expected digits.pdf): {p.name}")
            raise SystemExit(2)
        downloaded_ids.append(sid)

    missing = [sid for sid in downloaded_ids if sid not in id_to_student_number]
    if missing:
        Path("missing_ids.txt").write_text("\n".join(missing) + "\n", encoding="utf-8")
        print(f"❌ {len(missing)} IDs from PDFs were not found in {POWERSCHOOL_EXPORT}.")
        print("   Wrote missing list to missing_ids.txt")
        raise SystemExit(2)

    # Check duplicate student_numbers among the downloaded set
    seen_sn: dict[str, str] = {}
    dupes: list[str] = []
    for sid in downloaded_ids:
        sn = id_to_student_number[sid]
        if sn in seen_sn and seen_sn[sn] != sid:
            dupes.append(f"student_number {sn} mapped from IDs {seen_sn[sn]} and {sid}")
        else:
            seen_sn[sn] = sid

    if dupes:
        Path("duplicate_student_numbers.txt").write_text("\n".join(dupes) + "\n", encoding="utf-8")
        print("❌ Duplicate student_number mapping detected (data issue).")
        print("   Wrote details to duplicate_student_numbers.txt")
        raise SystemExit(2)

    # Refuse if input folder isn't empty (safety)
    if not folder_is_empty(INPUT_DIR):
        print(f"❌ Safety stop: {INPUT_DIR} must be empty before renaming/moving.")
        raise SystemExit(2)

    moved = 0
    for p in downloaded_pdfs:
        sid = extract_id_from_filename(p)
        assert sid is not None
        sn = id_to_student_number[sid]
        new_name = f"{sn}.pdf"  # always append .pdf here
        dest = INPUT_DIR / new_name

        if dest.exists():
            print(f"❌ Collision: destination already exists: {dest.name}")
            raise SystemExit(2)

        shutil.move(str(p), str(dest))
        moved += 1

    print(f"✅ Renamed+Moved {moved} PDFs into {INPUT_DIR}/")

def create_overlay_for_page(student_id: str, page) -> PdfReader:
    """
    Create an overlay PDF matching the size of the target page
    so coordinates are consistent even if not letter-sized.
    """
    buffer = BytesIO()

    # page.mediabox gives dimensions in PDF points
    width = float(page.mediabox.width)
    height = float(page.mediabox.height)

    c = canvas.Canvas(buffer, pagesize=(width, height))
    c.setFont(OVERLAY_FONT, OVERLAY_FONT_SIZE)
    c.drawString(OVERLAY_X, OVERLAY_Y, f"{OVERLAY_TEXT_PREFIX}{student_id}")
    c.save()

    buffer.seek(0)
    return PdfReader(buffer)

def inject_student_id_into_folder() -> None:
    """
    Reads PDFs in input_pdfs/, writes stamped PDFs into output_pdfs/
    with the same filename.
    """
    # Refuse if output folder isn't empty (safety)
    if not folder_is_empty(OUTPUT_DIR):
        print(f"❌ Safety stop: {OUTPUT_DIR} must be empty before stamping PDFs.")
        raise SystemExit(2)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    pdfs = sorted([p for p in INPUT_DIR.iterdir() if p.is_file() and p.suffix.lower() == ".pdf"])
    if not pdfs:
        print(f"❌ No PDFs found in {INPUT_DIR}/ to stamp.")
        raise SystemExit(2)

    stamped = 0
    for pdf_path in pdfs:
        student_id = pdf_path.stem  # filename is student_number now
        original_pdf = PdfReader(str(pdf_path))
        writer = PdfWriter()

        first_page = original_pdf.pages[0]
        overlay_pdf = create_overlay_for_page(student_id, first_page)
        first_page.merge_page(overlay_pdf.pages[0])
        writer.add_page(first_page)

        for page in original_pdf.pages[1:]:
            writer.add_page(page)

        out_path = OUTPUT_DIR / pdf_path.name
        with open(out_path, "wb") as f:
            writer.write(f)

        stamped += 1

    print(f"✅ Stamped {stamped} PDFs into {OUTPUT_DIR}/")

def chunked(lst, n):
    for i in range(0, len(lst), n):
        yield lst[i:i+n]

def combine_output_pdfs() -> None:
    # Refuse if combined folder isn't empty (safety)
    if not folder_is_empty(COMBINED_DIR):
        print(f"❌ Safety stop: {COMBINED_DIR} must be empty before combining PDFs.")
        raise SystemExit(2)

    COMBINED_DIR.mkdir(parents=True, exist_ok=True)

    pdfs = sorted([p for p in OUTPUT_DIR.iterdir() if p.is_file() and p.suffix.lower() == ".pdf"])
    if not pdfs:
        print(f"❌ No PDFs found in {OUTPUT_DIR}/ to combine.")
        raise SystemExit(2)

    print(f"Found {len(pdfs)} PDFs to combine (batch size = {BATCH_SIZE})")

    batch_num = 1
    for group in chunked(pdfs, BATCH_SIZE):
        out_path = COMBINED_DIR / f"combined_{batch_num:04d}.pdf"

        merger = PdfMerger()
        added = 0

        for pdf_path in group:
            try:
                merger.append(str(pdf_path))
                added += 1
            except Exception as e:
                print(f"⚠️  Failed to add {pdf_path.name}: {e}")

        if added == 0:
            print(f"❌ No PDFs added for batch {batch_num}; skipping write.")
            merger.close()
            batch_num += 1
            continue

        with open(out_path, "wb") as f:
            merger.write(f)

        merger.close()
        print(f"✅ Wrote {out_path.name} ({added} PDFs)")
        batch_num += 1

    print(f"✅ Combined PDFs are in {COMBINED_DIR}/")

def main():
    ensure_dirs()
    refuse_if_not_empty()

    print("=== DIBELS PDF Pipeline Wizard ===\n")
    print(f"1) Copy DIBELS PDFs (named like 123456.pdf) into: {DOWNLOADED_DIR}/")
    pause("When you have copied the PDFs, continue.")

    downloaded_pdfs = list_downloaded_pdfs()
    if not downloaded_pdfs:
        print(f"❌ No PDFs found in {DOWNLOADED_DIR}/")
        raise SystemExit(2)

    # Validate filenames and build ID list
    ids = []
    bad_names = []
    for p in downloaded_pdfs:
        sid = extract_id_from_filename(p)
        if sid is None:
            bad_names.append(p.name)
        else:
            ids.append(sid)

    if bad_names:
        Path("bad_filenames.txt").write_text("\n".join(bad_names) + "\n", encoding="utf-8")
        print("❌ Some PDFs do not match expected format digits.pdf")
        print("   Wrote list to bad_filenames.txt")
        raise SystemExit(2)

    write_id_lists(ids=ids, pdf_names=[p.name for p in downloaded_pdfs])
    print(f"✅ Wrote {ID_LIST_TXT} (IDs for PowerSchool paste)")
    print(f"✅ Wrote {FILE_LIST_CSV} (audit list of filenames)")

    print("\n2) PowerSchool step:")
    print(f"   - Open {ID_LIST_TXT} and copy the IDs")
    print("   - In PowerSchool, select those students and export fields using multiselct with the drop down set to Student ID: id and student_number")
    print(f"   - Save/export will produce: {POWERSCHOOL_EXPORT.name}")
    print("   - Copy that file into THIS working folder (same folder as run_pipeline.py)")
    pause(f"After copying {POWERSCHOOL_EXPORT.name} here, continue.")

    id_to_student_number = read_powerschool_export()
    print(f"✅ Read {len(id_to_student_number)} rows from {POWERSCHOOL_EXPORT.name}")

    print("\n3) Renaming and moving PDFs into input_pdfs/ as student_number.pdf ...")
    rename_and_move(downloaded_pdfs, id_to_student_number)

    print("\n4) Stamping PDFs (inserting student number onto first page) into output_pdfs/ ...")
    inject_student_id_into_folder()

    print("\n5) Combining PDFs into batches for upload ...")
    combine_output_pdfs()

    print("\n=== DONE ===")
    print(f"- Stamped PDFs: {OUTPUT_DIR}/")
    print(f"- Combined PDFs: {COMBINED_DIR}/")
    print("If you need smaller combined files, reduce BATCH_SIZE near the top and rerun (with empty folders).")

if __name__ == "__main__":
    main()
