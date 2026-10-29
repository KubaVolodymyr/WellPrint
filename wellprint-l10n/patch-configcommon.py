# Патч ConfigCommon.dll для діалогу білого («Union Set»→«Під каналами», «Negation»→«Інверсія»; інші мови — «Под каналами»/«Инверсия»).
# ЛИШЕ для ConfigCommon.dll з MD5 10adfe6b53b99fdafc424eecff4884c6: скрипт перевіряє очікувані байти й падає, якщо збірка інша. Робіть копію DLL. На свій ризик.
# Використання: python3 patch-configcommon.py ConfigCommon.dll.orig ConfigCommon.dll
import sys, struct, hashlib
b=bytearray(open(sys.argv[1],'rb').read()); f=lambda rva: rva-0x1000+0x400
def expect(off,h): assert bytes(b[off:off+len(bytes.fromhex(h))])==bytes.fromhex(h), f"@{off:#x}"
for rva in (0xb27d,0xb3c6): o=f(rva); expect(o,'83782803'); b[o+3]=0x0b
o=f(0xb3cc); expect(o,'41b809000000'); b[o+2]=0x10
o=f(0xb283); expect(o,'458d4608'); b[o+3]=0x10
def put(off,text,n,span):
    t=text.ljust(n).encode('utf-16le'); assert len(t)<=span; b[off:off+span]=t+b'\x00'*(span-len(t))
put(0xcaaa8,'Під каналами',16,32); put(0xcaa88,'Інверсія',16,32); expect(0xcaac8,'5f003000310000')
assert all(x==0 for x in b[0x12a95e:0x12aa00]); put(0x12a960,'Под каналами',12,32); put(0x12a980,'Инверсия',8,32)
o=f(0xb3e0); expect(o,'41b802000000'); b[o+2]=12
o=f(0xb298); expect(o,'41b802000000'); b[o+2]=8
o=f(0xb3e6); expect(o,'488d15cf0e0c00'); struct.pack_into('<i',b,o+3,0x12c160-0xb3ed)
o=f(0xb29e); expect(o,'488d15f70f0c00'); struct.pack_into('<i',b,o+3,0x12c180-0xb2a5)
pe=struct.unpack_from('<I',b,0x3c)[0]; optsz=struct.unpack_from('<H',b,pe+20)[0]; sh=pe+24+optsz+40
assert b[sh:sh+6]==b'.rdata' and struct.unpack_from('<I',b,sh+8)[0]==0x6215e; struct.pack_into('<I',b,sh+8,0x62200)
open(sys.argv[2],'wb').write(b); print("ok md5", hashlib.md5(b).hexdigest())
