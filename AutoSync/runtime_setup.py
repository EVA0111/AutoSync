"""Install dependencies from the desktop Setup panel; no batch scripts."""
import argparse,os,subprocess,sys
from pathlib import Path

def main():
 p=argparse.ArgumentParser();p.add_argument('--ai',action='store_true');args=p.parse_args()
 root=Path(__file__).resolve().parent
 bundled=root.parent/'python'/'python.exe'
 if bundled.is_file():
  if args.ai:
   subprocess.run([str(bundled),'-m','pip','install','--upgrade','--target',str(bundled.parent/'Lib/site-packages'),'faster-whisper>=1.1,<2','sentence-transformers>=3,<6'],check=True)
  else:
   subprocess.run([str(bundled),'-c','import numpy, scipy; print("Bundled engine is ready.")'],check=True)
  return
 env=root/'.venv';python=env/('Scripts/python.exe' if os.name=='nt' else 'bin/python')
 if not python.exists():
  print('Creating the AutoSync Python environment…',flush=True)
  subprocess.run([sys.executable,'-m','venv',str(env)],check=True)
 subprocess.run([str(python),'-m','pip','install','-r',str(root/'requirements.txt')],check=True)
 if args.ai:subprocess.run([str(python),'-m','pip','install','faster-whisper>=1.1,<2','sentence-transformers>=3,<6'],check=True)
 print('Setup complete. FFmpeg and FFprobe must be installed separately or placed beside AutoSync.',flush=True)
if __name__=='__main__':main()
