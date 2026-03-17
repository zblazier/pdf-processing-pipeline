# pdf-processing-pipeline
Document processing pipeline to transform DIBELS test results into a format that can be read by School Messenger

# PDF Processing Pipeline for Student Reports

## Overview
This project demonstrates an automated pipeline for processing student report PDFs, preparing them for distribution through mass communication systems.

The workflow handles renaming, data mapping, document stamping, and batch combining of PDFs.

---

## Problem
Student report PDFs are often:

- named using internal system IDs
- difficult to match to student-facing identifiers
- missing readable identifiers within the document
- required to be distributed in batch-friendly formats

Manual handling of these steps is time-consuming and error-prone.

---

## Solution
This pipeline automates the entire process:

1. Extract student IDs from downloaded PDF filenames
2. Map internal IDs to student numbers using a PowerSchool export
3. Rename and organize files
4. Inject readable student identifiers into PDFs
5. Combine PDFs into batch files for distribution

---

## Features

- Automated file validation and safety checks
- ID extraction and mapping from external data source
- PDF text overlay (student identifier injection)
- Batch processing and file combination
- Error handling for:
  - missing mappings
  - duplicate IDs
  - invalid filenames
  - unsafe folder states

---

## Technologies Used

- Python
- PyPDF2
- reportlab
- CSV processing
- file system automation

   
