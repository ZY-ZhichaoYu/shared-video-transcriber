"""Package only Git-indexed source files; refuse private/runtime artifacts."""
import argparse
import hashlib
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from version import __version__

PRIVATE_ROOTS={'.data','.venv','.git','.setup-logs','downloads','models','dist','tmp','test-results','__pycache__'}
PRIVATE_SUFFIXES={'.mp4','.mkv','.webm','.wav','.m4a','.flac','.mp3','.sqlite','.sqlite3','.db','.log','.pem','.key','.p12','.pyc','.bin'}


def validate_files(root,names):
    result=[]
    for name in names:
        relative=Path(name)
        if (relative.is_absolute() or '..' in relative.parts or any(p in PRIVATE_ROOTS for p in relative.parts)
                or relative.suffix.lower() in PRIVATE_SUFFIXES
                or (relative.name.startswith('.env') and relative.name!='.env.example')
                or relative.name in {'REFACTOR_REPORT.md','.setup.lock'}):
            raise ValueError('Refusing private/runtime artifact: '+name)
        path=root/relative
        if path.is_symlink() or not path.resolve().is_relative_to(root.resolve()) or not path.is_file():
            raise ValueError('Unsafe or missing source file: '+name)
        if path.stat().st_size>5*1024*1024:
            raise ValueError('Unexpectedly large source file: '+name)
        result.append(path)
    if not result:raise ValueError('No indexed source files')
    return result


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',default=str(ROOT/'dist'/f'video-inbox-{__version__}-source.zip'))
    parser.add_argument('--include-untracked',action='store_true',help='Preview uncommitted source; ignored files remain excluded')
    options=parser.parse_args()
    command=['git','ls-files','-z']
    if options.include_untracked:command+=['--cached','--others','--exclude-standard']
    names=list(dict.fromkeys(subprocess.check_output(command,cwd=ROOT).decode('utf-8').rstrip('\0').split('\0')))
    paths=validate_files(ROOT,names)
    output=Path(options.output).resolve();output.parent.mkdir(parents=True,exist_ok=True)
    checksum=output.with_suffix(output.suffix+'.sha256')
    if output.exists() or checksum.exists():raise ValueError('Output already exists; use a new output name')
    with zipfile.ZipFile(output,'x',zipfile.ZIP_DEFLATED) as archive:
        for path in paths:
            archive.write(path,'video-inbox/'+path.relative_to(ROOT).as_posix())
    digest=hashlib.sha256(output.read_bytes()).hexdigest()
    with checksum.open('x',encoding='ascii') as stream:stream.write(digest+'  '+output.name+'\n')
    print(f'{output.name}: {len(paths)} files, {output.stat().st_size} bytes, SHA256 {digest}')


if __name__=='__main__':main()
