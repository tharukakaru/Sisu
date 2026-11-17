"""Upgrade production dependencies using the patches verified on preview."""
from pathlib import Path
import hashlib, os, pwd, shutil, subprocess, tarfile, json
from datetime import datetime, timezone
ROOT=Path('/home/sisu/frappe-bench')
PROD=Path('/home/sisu/frappe-invoice-test')
ARCHIVE=Path('/tmp/sisu-security-dependencies.tgz')
DIGEST='946e0fce862c79427bcd229b2253395469546a60bd8d7de80438437a1c920eaf'
REVISIONS={'frappe':'980bdb0aa497ef787679353e0dbc16fd7cefbb36','lms':'389d8a2720bfbd4b2e0de3f0f3c15d4cf0485d1e'}
def main():
 if '--apply' not in __import__('sys').argv: raise RuntimeError('Pass --apply for the production upgrade')
 if os.geteuid()!=0: raise RuntimeError('Run as root')
 import fcntl
 lock=open('/var/lock/sisu-merged-deployment.lock','a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 if ROOT.is_symlink() or (ROOT/'env').resolve()==(PROD/'env').resolve(): raise RuntimeError('Unexpected environment')
 for app in ('frappe','lms','institute_lms'):
  if (ROOT/'apps'/app).resolve()==(PROD/'apps'/app).resolve(): raise RuntimeError('Shared application path')
 if hashlib.sha256(ARCHIVE.read_bytes()).hexdigest()!=DIGEST: raise RuntimeError('Archive checksum mismatch')
 with tarfile.open(ARCHIVE) as archive:
  members=archive.getmembers()
  if len(members)!=3 or {m.name for m in members}!={'frappe.patch','lms.patch','constraints.txt'} or not all(m.isfile() for m in members): raise RuntimeError('Unexpected payload')
  payload={m.name:archive.extractfile(m).read() for m in members}
 user=pwd.getpwnam('sisu')
 backup=Path('/home/sisu/.sisu-secrets')/('production-security-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'))
 backup.mkdir(mode=0o700);os.chown(backup,user.pw_uid,user.pw_gid)
 print('Private log:',backup/'upgrade.log',flush=True)
 with (backup/'upgrade.log').open('w') as log:
  def run(args,cwd=ROOT):
   return subprocess.run(['sudo','-H','-u','sisu','--',*args],cwd=cwd,stdout=log,stderr=log,check=True)
  pending=[]
  for app,revision in REVISIONS.items():
   root=ROOT/'apps'/app
   actual=subprocess.check_output(['sudo','-H','-u','sisu','--','git','rev-parse','HEAD'],cwd=root,text=True).strip()
   if actual!=revision: raise RuntimeError(app+' revision changed')
   patch=backup/(app+'.patch');patch.write_bytes(payload[app+'.patch']);os.chown(patch,user.pw_uid,user.pw_gid)
   reverse=subprocess.run(['sudo','-H','-u','sisu','--','git','apply','--reverse','--check',str(patch)],cwd=root,stdout=log,stderr=log)
   if reverse.returncode:
    run(['git','apply','--check',str(patch)],root);pending.append((root,patch))
   shutil.copy2(root/'pyproject.toml',backup/(app+'-pyproject.toml'))
  constraints=backup/'constraints.txt';constraints.write_bytes(payload['constraints.txt']+b'\npyotp==2.9.0\n');os.chown(constraints,user.pw_uid,user.pw_gid)
  uv=shutil.which('uv')
  if not uv: raise RuntimeError('uv not found; no packages or services changed')
  run([uv,'pip','freeze','--python',str(ROOT/'env/bin/python')])
  print('Backing up production Python environment...',flush=True)
  shutil.copytree(ROOT/'env',backup/'env',symlinks=True)
  subprocess.run(['supervisorctl','stop','frappe-bench-web:frappe-bench-frappe-web','frappe-bench-workers:'],check=True)
  try:
   for root,patch in pending:run(['git','apply',str(patch)],root)
   run([uv,'pip','install','--python',str(ROOT/'env/bin/python'),'-e','apps/frappe','-e','apps/lms','-e','apps/institute_lms','-c',str(constraints)])
   run([uv,'pip','check','--python',str(ROOT/'env/bin/python')])
   run([str(ROOT/'env/bin/python'),'-c','import frappe, lms, PIL, pypdf, lxml, markdown, git, filelock; print("Imports passed")'])
   subprocess.run(['supervisorctl','start','frappe-bench-web:frappe-bench-frappe-web','frappe-bench-workers:'],check=True)
   print('PRODUCTION DEPENDENCIES UPDATED. Compatibility checks passed; web/workers started. Proceed with the application installer.',flush=True)
  except Exception:
   print('Upgrade failed; restoring previous environment and manifests.',flush=True)
   subprocess.run(['supervisorctl','stop','frappe-bench-web:frappe-bench-frappe-web','frappe-bench-workers:'],stdout=log,stderr=log)
   for app in REVISIONS:
    shutil.copy2(backup/(app+'-pyproject.toml'),ROOT/'apps'/app/'pyproject.toml')
    os.chown(ROOT/'apps'/app/'pyproject.toml',user.pw_uid,user.pw_gid)
   os.rename(ROOT/'env',backup/'failed-env')
   os.rename(backup/'env',ROOT/'env')
   for parent,dirs,files in os.walk(ROOT/'env'):
    os.chown(parent,user.pw_uid,user.pw_gid)
    for name in dirs+files:os.chown(Path(parent)/name,user.pw_uid,user.pw_gid,follow_symlinks=False)
   subprocess.run(['supervisorctl','start','frappe-bench-web:frappe-bench-frappe-web','frappe-bench-workers:'],check=True)
   print('Previous dependencies restored. Private log:',backup,flush=True)
   raise
if __name__=='__main__':main()
