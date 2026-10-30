"""Install optional components without changing Standard synchronization."""
import argparse,os,subprocess,sys
from pathlib import Path

def main():
 p=argparse.ArgumentParser()
 p.add_argument('--ai',action='store_true',help='Install optional subtitle AI')
 p.add_argument('--sync-ai',action='store_true',help='Install optional AST/DINOv2 syncing dependencies')
 args=p.parse_args()
 if args.ai and args.sync_ai:p.error('Choose one optional setup type.')
 root=Path(__file__).resolve().parent
 bundled=root.parent/'python'/'python.exe'
 if bundled.is_file():
  if args.sync_ai:
   print('Installing optional AI-assisted sync dependencies. The package download may be large.',flush=True)
   subprocess.run([str(bundled),'-m','pip','install','--upgrade','--target',
       str(bundled.parent/'ai-sync-packages'),'-r',str(root/'requirements-sync-ai.txt')],check=True)
   print('AI Sync setup complete. Pretrained AST and DINOv2 weights download on first analysis.',flush=True)
  elif args.ai:
   subprocess.run([str(bundled),'-m','pip','install','--upgrade','--target',
       str(bundled.parent/'Lib/site-packages'),'faster-whisper>=1.1,<2','sentence-transformers>=3,<6'],check=True)
  else:
   subprocess.run([str(bundled),'-c','import numpy, scipy; print("Bundled engine is ready.")'],check=True)
  return
 env=root/'.venv';python=env/('Scripts/python.exe' if os.name=='nt' else 'bin/python')
 if not python.exists():
  print('Creating the AutoSync Python environment…',flush=True)
  subprocess.run([sys.executable,'-m','venv',str(env)],check=True)
 subprocess.run([str(python),'-m','pip','install','-r',str(root/'requirements.txt')],check=True)
 if args.ai:subprocess.run([str(python),'-m','pip','install','faster-whisper>=1.1,<2','sentence-transformers>=3,<6'],check=True)
 if args.sync_ai:
  subprocess.run([str(python),'-m','pip','install','-r',str(root/'requirements-sync-ai.txt')],check=True)
  print('AI Sync setup complete. Pretrained weights download on first analysis.',flush=True)
 print('Setup complete. FFmpeg and FFprobe must be installed or bundled.',flush=True)
if __name__=='__main__':main()
