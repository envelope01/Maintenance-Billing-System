import os
import shutil
import platform
import subprocess


def detect_pdf_engine():

    system = platform.system()

    # -------------------------
    # WINDOWS
    # -------------------------
    if system == "Windows":

        try:
            import win32com.client
            import pythoncom

            pythoncom.CoInitialize()

            word = win32com.client.gencache.EnsureDispatch("Word.Application")
            word.Quit()

            return "word"

        except Exception:
            pass

        libreoffice_paths = [
            r"C:\Program Files\LibreOffice\program\soffice.exe",
            r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
        ]

        for path in libreoffice_paths:
            if os.path.exists(path):
                return path

        if shutil.which("soffice"):
            return shutil.which("soffice")

        if shutil.which("libreoffice"):
            return shutil.which("libreoffice")

    # -------------------------
    # LINUX / STREAMLIT CLOUD
    # -------------------------
    elif system == "Linux":

        if shutil.which("libreoffice"):
            return shutil.which("libreoffice")

        if shutil.which("soffice"):
            return shutil.which("soffice")

    return None


def convert_with_word(docx_file, pdf_file, word_app=None):

    we_opened_word = False

    if word_app is None:

        import pythoncom
        import win32com.client

        pythoncom.CoInitialize()

        word_app = win32com.client.gencache.EnsureDispatch("Word.Application")
        word_app.Visible = False

        we_opened_word = True

    doc = None

    try:

        doc = word_app.Documents.Open(os.path.abspath(docx_file))

        # Save as PDF
        doc.SaveAs2(
            os.path.abspath(pdf_file),
            FileFormat=17
        )

    finally:

        if doc is not None:
            try:
                doc.Close(False)
            except Exception:
                pass

        if we_opened_word:
            try:
                word_app.Quit()
            except Exception:
                pass


def convert_with_libreoffice(
    soffice_path,
    docx_file,
    pdf_dir
):

    subprocess.run(
        [
            soffice_path,
            "--headless",
            "--convert-to",
            "pdf",
            docx_file,
            "--outdir",
            pdf_dir,
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def convert_docx_to_pdf(
    docx_file,
    pdf_dir,
    engine=None,
    word_app=None
):

    if engine is None:
        engine = detect_pdf_engine()

    if engine is None:
        raise RuntimeError(
            "No PDF conversion engine found."
        )

    pdf_file = os.path.join(
        pdf_dir,
        os.path.basename(docx_file).replace(".docx", ".pdf")
    )

    if engine == "word":

        convert_with_word(
            docx_file,
            pdf_file,
            word_app=word_app
        )

    else:

        convert_with_libreoffice(
            engine,
            docx_file,
            pdf_dir
        )

    # Verify PDF was created
    if not os.path.exists(pdf_file):
        raise FileNotFoundError(
            f"PDF was not created:\n{pdf_file}"
        )

    return pdf_file