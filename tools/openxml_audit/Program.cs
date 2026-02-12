using System;
using System.IO;
using DocumentFormat.OpenXml;
using DocumentFormat.OpenXml.Packaging;
using DocumentFormat.OpenXml.Validation;

namespace OpenXmlAudit
{
    internal static class Program
    {
        private const int DefaultMaxErrors = 25;

        public static int Main(string[] args)
        {
            if (args.Length == 0)
            {
                Console.Error.WriteLine("Usage: openxml-audit <file.pptx> [file2.pptx ...]");
                return 2;
            }

            int maxErrors = DefaultMaxErrors;
            string? maxEnv = Environment.GetEnvironmentVariable("OPENXML_MAX_ERRORS");
            if (int.TryParse(maxEnv, out int parsed) && parsed > 0)
            {
                maxErrors = parsed;
            }

            bool anyErrors = false;
            foreach (string path in args)
            {
                if (!File.Exists(path))
                {
                    Console.Error.WriteLine($"{path}: file not found");
                    anyErrors = true;
                    continue;
                }

                try
                {
                    using PresentationDocument doc = PresentationDocument.Open(path, false);
                    OpenXmlValidator validator = new OpenXmlValidator(FileFormatVersions.Office2016);
                    int count = 0;

                    foreach (ValidationErrorInfo error in validator.Validate(doc))
                    {
                        count++;
                        if (count <= maxErrors)
                        {
                            string part = error.Part?.Uri?.ToString() ?? "";
                            string location = error.Path?.XPath ?? "";
                            Console.WriteLine($"{path}: {error.Description} (part={part}, path={location})");
                        }
                    }

                    if (count > maxErrors)
                    {
                        Console.WriteLine($"{path}: ... {count - maxErrors} more errors");
                    }

                    if (count > 0)
                    {
                        Console.WriteLine($"{path}: FAIL ({count} errors)");
                        anyErrors = true;
                    }
                    else
                    {
                        Console.WriteLine($"{path}: OK");
                    }
                }
                catch (Exception ex)
                {
                    Console.Error.WriteLine($"{path}: validator error: {ex.Message}");
                    anyErrors = true;
                }
            }

            return anyErrors ? 1 : 0;
        }
    }
}
