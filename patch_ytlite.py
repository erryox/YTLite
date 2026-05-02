#!/usr/bin/env python3
import sys
import os
import subprocess
import tempfile
import shutil
import lzma

PATCH_BYTES = bytes([0x00, 0x80, 0xd2, 0x00, 0xc0, 0x03, 0x5f, 0xd6, 0x1f, 0x20, 0x03, 0xd5])

def patch_deb(input_deb, output_deb):
    tmp_dir = tempfile.mkdtemp()

    try:
        subprocess.run(['ar', 'x', os.path.abspath(input_deb)], cwd=tmp_dir, check=True)

        data_file = None
        for f in ['data.tar.lzma', 'data.tar.xz']:
            path = os.path.join(tmp_dir, f)
            if os.path.exists(path):
                data_file = path
                break

        if not data_file:
            raise Exception("data file not found")

        if data_file.endswith('.lzma') or data_file.endswith('.xz'):
            xz_out = subprocess.check_output(['xz', '-d', '-c', data_file])
            with open(os.path.join(tmp_dir, 'data.tar'), 'wb') as f:
                f.write(xz_out)

        subprocess.run(['tar', '-xf', os.path.join(tmp_dir, 'data.tar')], cwd=tmp_dir, check=True)

        dylib = os.path.join(tmp_dir, 'Library', 'MobileSubstrate', 'DynamicLibraries', 'YTLite.dylib')
        if not os.path.exists(dylib):
            raise Exception("YTLite.dylib not found")

        result = subprocess.run(['otool', '-tV', dylib], capture_output=True, text=True)
        lines = result.stdout.split('\n')
        vmaddr = None
        for i, line in enumerate(lines):
            if line.strip() == '_dvnLocked:':
                if i + 1 < len(lines):
                    next_line = lines[i + 1].strip()
                    if next_line:
                        vmaddr = int(next_line.split()[0], 16)
                        break

        if vmaddr is None:
            raise Exception("_dvnLocked not found")

        print(f"Patching _dvnLocked at 0x{vmaddr:x}")
        with open(dylib, 'r+b') as f:
            f.seek(vmaddr)
            f.write(PATCH_BYTES)

        data_tar = os.path.join(tmp_dir, 'data.tar')
        data_lzma = os.path.join(tmp_dir, 'data.tar.lzma')

        if os.path.exists(data_lzma):
            os.remove(data_lzma)
        if os.path.exists(data_tar):
            os.remove(data_tar)

        subprocess.run(['tar', '-cf', data_tar, 'Library/'], cwd=tmp_dir, check=True)

        with open(data_tar, 'rb') as f:
            tar_data = f.read()

        with lzma.open(data_lzma, 'wb', preset=9) as f:
            f.write(tar_data)

        with open(os.path.join(tmp_dir, 'debian-binary'), 'w') as f:
            f.write('2.0\n')

        output_path = os.path.abspath(output_deb)
        subprocess.run(['ar', 'rcs', output_path,
                       os.path.join(tmp_dir, 'debian-binary'),
                       os.path.join(tmp_dir, 'control.tar.gz'),
                       os.path.join(tmp_dir, 'data.tar.lzma')], check=True)

        print(f"Created: {output_path}")

    finally:
        shutil.rmtree(tmp_dir)

if __name__ == '__main__':
    if len(sys.argv) < 3:
        print(f"Usage: {sys.argv[0]} <input.deb> <output.deb>")
        sys.exit(1)

    input_deb = sys.argv[1]
    output_deb = sys.argv[2]

    if not os.path.exists(input_deb):
        print(f"Error: {input_deb} not found")
        sys.exit(1)

    try:
        patch_deb(input_deb, output_deb)
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)