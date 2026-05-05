from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
import os

try:
    # Create a new PDF with ReportLab
    c = canvas.Canvas('test.pdf', pagesize=letter)
    width, height = letter

    # Add some content to the PDF
    c.drawString(100, height - 100, 'Hello, World!')
    c.drawString(100, height - 150, 'This is a test PDF created with ReportLab.')
    c.drawString(100, height - 200, 'Thank you for using this service!')

    # Save the PDF
    c.save()
    
    # Check if file was created
    if os.path.exists('test.pdf'):
        print('PDF created successfully as test.pdf')
        print(f'File size: {os.path.getsize("test.pdf")} bytes')
    else:
        print('Failed to create PDF file')
        
except Exception as e:
    print(f'Error creating PDF: {e}')