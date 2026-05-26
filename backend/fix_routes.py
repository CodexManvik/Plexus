#!/usr/bin/env python
"""Fix the route ordering in contracts.py"""

# Read the file
with open('app/routes/contracts.py', 'r') as f:
    lines = f.readlines()

# Find line numbers for key routes
search_start = None
id_start = None

for i, line in enumerate(lines):
    if '@router.get("/search"' in line:
        search_start = i
    elif '@router.get("/{id}"' in line:
        id_start = i
        break

print(f"Found search endpoint at line {search_start + 1}")
print(f"Found /{'{'}id{'}'} endpoint at line {id_start + 1}")

# Extract and reorder
before_id = lines[:id_start]
search_block = lines[search_start:]
between = lines[id_start:search_start]

# Reconstruct: before_id + search_block + between
new_lines = before_id + search_block + between

# Write back
with open('app/routes/contracts.py', 'w') as f:
    f.writelines(new_lines)

print("Routes reordered successfully!")
