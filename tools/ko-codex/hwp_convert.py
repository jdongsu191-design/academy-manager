"""Render HWP/HWPX through installed Hancom, without altering security settings."""
import hashlib
import io
import os
from pathlib import Path
import subprocess
import sys
import zipfile
import json
import uuid
import pymupdf


def validate_document(blob, extension):
    if extension == 'pdf':
        valid = blob.startswith(b'%PDF-')
    elif extension == 'hwp':
        valid = blob.startswith(bytes.fromhex('d0cf11e0a1b11ae1'))
    elif extension == 'hwpx':
        try:
            with zipfile.ZipFile(io.BytesIO(blob)) as archive:
                valid = 'Contents/content.hpf' in archive.namelist()
                if len(archive.infolist()) > 10000 or sum(f.file_size for f in archive.infolist()) > 200*1024*1024:
                    raise ValueError('한글 문서의 압축 해제 크기가 너무 큽니다.')
        except zipfile.BadZipFile:
            valid = False
    else:
        raise ValueError('PDF, HWP, HWPX만 지원합니다.')
    if not valid:
        raise ValueError('선택한 확장자와 문서 형식이 일치하지 않습니다.')


def to_pdf(blob, extension, folder, progress):
    validate_document(blob, extension)
    if extension == 'pdf':
        return blob
    if os.name != 'nt':
        raise ValueError('한글 변환은 한컴 한글이 설치된 Windows 처리기에서 지원합니다.')
    digest = hashlib.sha256(extension.encode()+blob).hexdigest()
    cache = folder.parent/'converted'/digest
    cache.mkdir(parents=True, exist_ok=True)
    target = cache/'converted.pdf'
    if target.exists() and target.read_bytes().startswith(b'%PDF-'):
        return target.read_bytes()
    source = cache/('source.'+extension)
    source.write_bytes(blob)
    candidate = cache/(uuid.uuid4().hex+'.pdf')
    progress('한글 원본을 PDF로 변환 중 · 한글 파일 접근 확인창이 뜨면 허용해 주세요.')
    try:
        with (cache/'convert.log').open('w', encoding='utf-8') as log:
            result = subprocess.run([sys.executable, str(Path(__file__).resolve()), str(source), str(candidate)],
                                    stdout=log, stderr=log, timeout=180)
        if result.returncode or not candidate.exists() or candidate.stat().st_size > 80*1024*1024:
            raise ValueError('한글 변환 실패. 한글 설치·파일 접근 허용·문서 암호를 확인하고 다시 분석하세요. converted 폴더의 convert.log에 상세 내용이 있습니다.')
        expected = json.loads(candidate.with_suffix('.json').read_text(encoding='utf-8'))['pages']
        with pymupdf.open(candidate) as document:
            if document.needs_pass or len(document) != expected:
                raise ValueError('한글 원본과 변환 PDF의 페이지 수가 다릅니다. 원본을 확인하세요.')
        candidate.replace(target)
        return target.read_bytes()
    except subprocess.TimeoutExpired:
        raise ValueError('한글 변환 대기 시간 초과. 한글의 파일 접근 확인창을 확인하고 다시 분석하세요.') from None


def close_conversion_document(hwp, source, target):
    paths = (str(source.resolve()), str(target.resolve()))
    if hwp.XHwpDocuments.Count == 1 and hwp.Path in paths:
        # hwpDiscard: discard only the verified temporary document before Quit.
        hwp.Clear(1)
        hwp.Quit()
    else:
        for i in range(hwp.XHwpDocuments.Count-1, -1, -1):
            document = hwp.XHwpDocuments.Item(i)
            if document.FullName in paths:
                document.Close(False)


def convert(source, target):
    import pythoncom
    import win32com.client
    pythoncom.CoInitialize()
    hwp = None
    owned = False
    try:
        hwp = win32com.client.DispatchEx('HWPFrame.HwpObject')
        # Never reuse or close an already-open user document.
        if hwp.XHwpDocuments.Count != 1 or hwp.Path:
            raise RuntimeError('독립된 한글 변환 창을 만들지 못했습니다.')
        owned = True
        # Keep Hancom's own file-access prompt available; never auto-approve it.
        hwp.XHwpWindows.Item(0).Visible = True
        print('Opening document; approve Hancom file-access prompt if shown.', flush=True)
        if not hwp.Open(str(source.resolve()), '', ''):
            raise RuntimeError('한글 문서를 열지 못했습니다.')
        pages = hwp.PageCount
        if not 1 <= pages <= 30:
            raise RuntimeError('1~30쪽 한글 시험지를 사용하세요.')
        print('Exporting PDF.', flush=True)
        if not hwp.SaveAs(str(target.resolve()), 'PDF', ''):
            raise RuntimeError('한글 PDF 저장 실패')
        target.with_suffix('.json').write_text(json.dumps({'pages':pages}),encoding='utf-8')
    finally:
        try:
            if hwp is not None and owned:
                close_conversion_document(hwp, source, target)
        finally:
            hwp = None
            pythoncom.CoUninitialize()


if __name__ == '__main__':
    convert(Path(sys.argv[1]), Path(sys.argv[2]))
