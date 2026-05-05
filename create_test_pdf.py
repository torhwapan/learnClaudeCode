from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

# Create a new PDF with ReportLab
c = canvas.Canvas("test.pdf", pagesize=letter)
width, height = letter  # Keep track of our page size

# Add some text to the PDF
c.drawString(100, 750, "Hello, World!")
c.drawString(100, 730, "This is a test PDF created with ReportLab.")
c.drawString(100, 710, "Created on: D:\\Professional\\myCode\\learnClaudeCode")

# Save the PDF
c.save()

print("PDF 'test.pdf' has been created successfully!")