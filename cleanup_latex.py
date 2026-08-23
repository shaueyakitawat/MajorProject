"""
Cleanup script for latexcode:
1. Remove all pure-comment lines (lines starting with % that are template boilerplate)
2. Collapse runs of 3+ blank lines into a single blank line
3. Remove stray dots on their own lines
4. Keep essential LaTeX comments (like % inside \author blocks, or %% figure insertion markers)
"""
import re

INPUT  = r"d:\MajorProject\latexcode"
OUTPUT = r"d:\MajorProject\latexcode"

with open(INPUT, "r", encoding="utf-8") as f:
    lines = f.readlines()

cleaned = []
for line in lines:
    stripped = line.strip()

    # Remove lines that are ONLY a comment (start with % or %%) and are template boilerplate
    # Keep lines that have actual LaTeX commands mixed with comments
    if stripped.startswith("%") or stripped.startswith("%%"):
        # Keep figure/table insertion markers that reference our actual figures
        if any(kw in stripped.lower() for kw in [
            "insert figure", "insert table", "insert comparison",
            "insert option", "forecast accuracy", "suggested filename",
            "includegraphics"
        ]):
            cleaned.append(line)
            continue
        # Keep \ifCLASSOPTION lines (they are functional)
        if "\\if" in stripped or "\\fi" in stripped:
            cleaned.append(line)
            continue
        # Skip all other pure comment lines
        continue

    # Remove stray single dots on their own line
    if stripped == ".":
        continue

    cleaned.append(line)

# Collapse multiple consecutive blank lines (3+) into 1
result = []
blank_count = 0
for line in cleaned:
    if line.strip() == "":
        blank_count += 1
        if blank_count <= 1:
            result.append(line)
    else:
        blank_count = 0
        result.append(line)

# Remove the \ifCLASSOPTIONcaptionsoff block entirely since it's boilerplate
final = []
skip_block = False
for line in result:
    stripped = line.strip()
    if stripped == "\\ifCLASSOPTIONcaptionsoff":
        skip_block = True
        continue
    if skip_block and stripped == "\\fi":
        skip_block = False
        continue
    if skip_block:
        continue
    final.append(line)

with open(OUTPUT, "w", encoding="utf-8") as f:
    f.writelines(final)

print(f"Cleanup complete. {len(lines)} lines -> {len(final)} lines.")
