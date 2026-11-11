// Print the text an ATS parser would extract from a PDF (macOS PDFKit).
// Usage: swift scripts/pdf-text.swift <file.pdf>
import Foundation
import PDFKit

guard CommandLine.arguments.count == 2,
      let doc = PDFDocument(url: URL(fileURLWithPath: CommandLine.arguments[1])) else {
    FileHandle.standardError.write("usage: swift pdf-text.swift <file.pdf>\n".data(using: .utf8)!)
    exit(1)
}
print(doc.string ?? "")
