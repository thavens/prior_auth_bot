# Motivation

We want to find Prior Authorization documents that apply for the provider we're looking for.

For the now this will just be hardcoded for testing purposes.

# Context

Results of the following task will be passed to the [document_population.md](document_population.md)

# Task

1. Curl the link https://medi-calrx.dhcs.ca.gov/cms/medicalrx/static-assets/documents/provider/forms-and-information/Medi-Cal_Rx_PA_Request_Form.pdf#page=1.00&gsr=0
2. Write a pymupdf script that will take the pdf and number label each of the AcroForm fields. Over each of the AcroForm fields it should paste a string and number, where the string corresponds to the widget type and number number is the ith index of that widget type. The pasted format should be "<widget_type>_<i>"
3. Save the an s3 bucket for documents.
4. Run the textract on the document.
5. Save the textract to the textract s3 bucket.

# Requirements

S3 services and names should put put into the current_services.md

## S3 Structure

Document bucket structure should have a folder in the root dir for each insurance provider. For now just medical.

## Textract S3 Structure

Textract output bucket should also have this structure where the documents are foldered by provider.