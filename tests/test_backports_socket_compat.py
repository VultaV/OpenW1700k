#!/usr/bin/env python3
"""Compile the actual patch guard against the 6.18 stable type transition.

Native fixtures reflect official linux/socket.h: 6.18.57-60 have the type,
6.18.61-64 do not. All keep __sockaddr_check_size, so it cannot detect this.
This is a header compatibility check, not a socket runtime test.
"""
from pathlib import Path
import subprocess,tempfile
r=Path(__file__).resolve().parents[1]
p=r/'package/kernel/mac80211/patches/build/310-backports-sockaddr_unsized-in-6.18.57.patch'
s=p.read_text();first=s.index('+#if ');end=s.index('\n /**',first)
guard='\n'.join(line[1:] for line in s[first:end].splitlines())
versions=[(6,18,56,False),(6,18,57,True),(6,18,58,True),(6,18,59,True),(6,18,60,True),(6,18,61,False),(6,18,62,False),(6,18,63,False),(6,18,64,False),(6,19,0,True),(7,2,0,True)]
with tempfile.TemporaryDirectory(prefix='socket-compat-') as t:
 root=Path(t)
 for a,b,c,native in versions:
  code=f'#define CURRENT (({a}<<16)+({b}<<8)+{c})\n'
  code+='#define KVER(a,b,c) (((a)<<16)+((b)<<8)+(c))\n#define LINUX_VERSION_IS_LESS(a,b,c) (CURRENT < KVER(a,b,c))\n#define LINUX_VERSION_IS_GEQ(a,b,c) (CURRENT >= KVER(a,b,c))\n'
  decl='struct sockaddr_unsized { unsigned short sa_family; char sa_data[]; };\n'
  if native:code+=decl
  code+=guard+'\n'+decl+'#endif\n_Static_assert(sizeof(struct sockaddr_unsized)==2,"type unavailable");\n'
  src=root/'check.c';src.write_text(code)
  subprocess.run(['cc','-std=c11','-Werror','-fsyntax-only',str(src)],capture_output=True,check=True)
 print(f'PASS: {len(versions)} kernel header type-availability cases')
