import os
os.environ["CUDA_VISIBLE_DEVICES"] = "-1"
import csv
import subprocess
import time
from datetime import datetime
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent
PDF_DIR = BASE_DIR / "input_pdfs"
OUT_DIR = BASE_DIR / "output_md"
LOG_DIR = BASE_DIR / "logs"

LOG_CSV = LOG_DIR / "parse_log.csv"
DETAIL_LOG = LOG_DIR / "parse_detail.log"

TIMEOUT_SECONDS = 60 * 40  # 单个PDF最多解析40分钟


def ensure_dirs():
    OUT_DIR.mkdir(exist_ok=True)
    LOG_DIR.mkdir(exist_ok=True)



def find_markdown_files(folder: Path):
    return list(folder.rglob("*.md"))


def write_detail_log(content: str):
    with DETAIL_LOG.open("a", encoding="utf-8") as f:
        f.write(content + "\n")


def run_mineru(pdf_path: Path, output_dir: Path):
    """
    调用MinerU解析PDF。
    已确认PDF为文本可复制型，因此不使用OCR。
    
    注意：
    不同版本MinerU命令参数可能略有差异。
    如果 mineru 命令不可用，可改用 magic-pdf。
    """

    company_out_dir = output_dir / pdf_path.stem
    company_out_dir.mkdir(parents=True, exist_ok=True)

    # 新版 MinerU 常见命令
    cmd = [
      "mineru",
      "-p", str(pdf_path),
      "-o", str(company_out_dir),
      "-m", "txt",
      "-b", "pipeline",
      "-l", "ch",
      "-f", "false",
      "-t", "false",
      "--image-analysis", "false"
    ]

    start_time = time.time()

    result = subprocess.run(
        cmd,
        timeout=TIMEOUT_SECONDS
    )

    duration = round(time.time() - start_time, 2)

    return result.returncode, "", "", duration, company_out_dir


def main():
    ensure_dirs()

    pdf_files = sorted(PDF_DIR.glob("*.pdf"))

    if not pdf_files:
        print(f"未在 {PDF_DIR} 中找到PDF文件")
        return

    with LOG_CSV.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)

        writer.writerow([
            "序号",
            "文件名",
            "解析模式",
            "状态",
            "开始时间",
            "结束时间",
            "耗时秒",
            "输出目录",
            "Markdown文件数",
            "错误信息"
        ])

        for index, pdf_path in enumerate(pdf_files, start=1):
            start_dt = datetime.now()
            start_str = start_dt.strftime("%Y-%m-%d %H:%M:%S")

            print(f"\n开始解析：{pdf_path.name}")

            try:

                write_detail_log("=" * 80)
                write_detail_log(f"开始解析：{pdf_path.name}")
                write_detail_log(f"开始时间：{start_str}")
                write_detail_log("解析模式：txt，非OCR")

                returncode, stdout, stderr, duration, company_out_dir = run_mineru(
                    pdf_path,
                    OUT_DIR
                )

                end_dt = datetime.now()
                end_str = end_dt.strftime("%Y-%m-%d %H:%M:%S")

                md_files = find_markdown_files(company_out_dir)

                if returncode == 0:
                    status = "成功"
                    error_msg = ""
                else:
                    status = "失败"
                    error_msg = "" if returncode == 0 else "MinerU返回非0状态码"

                writer.writerow([
                    index,
                    pdf_path.name,
                    "txt_non_ocr",
                    status,
                    start_str,
                    end_str,
                    duration,
                    str(company_out_dir),
                    len(md_files),
                    error_msg
                ])

                write_detail_log(f"结束时间：{end_str}")
                write_detail_log(f"状态：{status}")
                write_detail_log(f"耗时秒：{duration}")
                write_detail_log(f"Markdown文件数：{len(md_files)}")

                print(f"完成：{pdf_path.name}，状态：{status}，耗时：{duration}秒")

            except subprocess.TimeoutExpired:
                end_dt = datetime.now()
                end_str = end_dt.strftime("%Y-%m-%d %H:%M:%S")

                writer.writerow([
                    index,
                    pdf_path.name,
                    "txt_non_ocr",
                    "超时",
                    start_str,
                    end_str,
                    TIMEOUT_SECONDS,
                    "",
                    0,
                    "单文件解析超过设定时间"
                ])

                write_detail_log(f"解析超时：{pdf_path.name}")
                print(f"超时：{pdf_path.name}")

            except Exception as e:
                end_dt = datetime.now()
                end_str = end_dt.strftime("%Y-%m-%d %H:%M:%S")

                writer.writerow([
                    index,
                    pdf_path.name,
                    "txt_non_ocr",
                    "异常",
                    start_str,
                    end_str,
                    "",
                    "",
                    0,
                    str(e)
                ])

                write_detail_log(f"解析异常：{pdf_path.name}")
                write_detail_log(str(e))
                print(f"异常：{pdf_path.name}，原因：{e}")


if __name__ == "__main__":
    main()