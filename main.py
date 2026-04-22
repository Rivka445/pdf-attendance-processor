from app.core.pipeline import run_pipeline

FILES = [
    "pdf files/a_r_9.pdf",
    "pdf files/a_r_25.pdf",
    "pdf files/n_r_5_n.pdf",
    "pdf files/n_r_10_n.pdf",
]

if __name__ == "__main__":
    for path in FILES:
        run_pipeline(path, n=3, formats=["pdf", "excel", "html"], output_dir="export")
