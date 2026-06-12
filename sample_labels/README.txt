Treasury Production Demonstration Dataset

Contents:
- 30 separate PNG alcohol label images (Batch_labels folder)
	- 15 expected PASS labels
	- 15 expected FAIL labels
- 9 separate PNG alcohol label images for individual testing (Individual Testing Labels folder)
- batch_expected_fields_samples.csv
- treasury_expected_results_manifest.csv

Coverage:
- Wine, whiskey, bourbon, tequila, vodka, gin, beer, rum, and mead
- Domestic and imported products
- Producer/importer names and addresses
- Country-of-origin examples
- Failure modes such as missing warning, missing importer, incomplete address,
  missing country of origin, glare, blur, rotated image, cropped image, tiny
  warning text, wrong net contents, wrong ABV, missing class/type, and COO mismatch

Usage:
- Upload the PNG files to the prototype individually or in batch mode.
- Use batch_expected_fields_samples.csv to upload as a batch processing file.

Reference:
- View the treasury_expected_results_manifest.csv as the expected results reference.
