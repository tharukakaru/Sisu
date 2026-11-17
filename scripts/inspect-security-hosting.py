"""Read-only hosting compatibility report. Never prints keys or full site configs."""
from pathlib import Path
import subprocess, json

PROBE = r'''
import importlib.metadata as m, json
names=['frappe','lms','filelock','GitPython','Pillow','pypdf','Markdown','lxml','redis']
for name in names:
 try:
  print(name, m.version(name))
  if name in ('frappe','lms'):
   for requirement in m.requires(name) or []:
    if any(n.lower() in requirement.lower() for n in names[2:]): print(' requires:',requirement)
 except m.PackageNotFoundError: print(name,'not installed')
'''
for root in (Path('/home/sisu/frappe-bench'),Path('/home/sisu/frappe-invoice-test')):
 print('BENCH:',root,flush=True)
 subprocess.run([str(root/'env/bin/python'),'-c',PROBE],check=True)
 for app in ('frappe','lms'):
  path=root/'apps'/app
  result=subprocess.run(['git','-c','safe.directory='+str(path),'rev-parse','HEAD'],cwd=path,text=True,capture_output=True)
  print(app,'revision:',result.stdout.strip() or 'unavailable')
  result=subprocess.run(['git','-c','safe.directory='+str(path),'diff','--numstat','--','pyproject.toml'],cwd=path,text=True,capture_output=True)
  print(app,'manifest changes:',result.stdout.strip() or 'none')
 for path in sorted((root/'sites').glob('*/site_config.json')):
  c=json.loads(path.read_text()); cap=c.get('il_checkout_recaptcha') or {}
  print('SITE:',path.parent.name,'host:',c.get('host_name'),'captcha_enabled:',cap.get('enabled',False),'captcha_hosts:',cap.get('hostnames',[]))
print('NGINX ROUTING (selected directives only):')
r=subprocess.run(['nginx','-T'],text=True,capture_output=True)
for line in r.stdout.splitlines():
 s=line.strip()
 if s.startswith(('server_name ','root ','alias ','proxy_pass ','proxy_set_header X-Forwarded-For ')):
  print(s)
print('Read-only inspection complete. No settings, packages or services changed.')
