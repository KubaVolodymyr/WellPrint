# Патч WellPrintMacExp.exe (MD5 оригіналу cb808a89dfea06a785555f7850741ba7): 8 склеєних підписів панелі «UV Lamp» → по одному запасному запису словника.
# Масиви номерів у .rdata (по 4 dword) → [spare, 97, 97, 97]; для 4 прапорців ще й дописуваний у коді Effective (0x8c) → 97 (порожній запис Custom_Wait_Print_Start_Signal).
# Тексти речень живуть у словнику в записах French/Portuguese/Korean/Spanish (прапорці), Turkish/Japanese (зміщення), Turkey/SinglePassMemOutstripDDrMem (засвітка) — правляться Блокнотом.
# Використання: python3 patch-wellprintexe-lamp.py WellPrintMacExp.exe.orig WellPrintMacExp.exe
import sys, struct, hashlib
b=bytearray(open(sys.argv[1],'rb').read()); assert hashlib.md5(b).hexdigest()=='cb808a89dfea06a785555f7850741ba7', 'інша збірка exe'
E=97
arrays={0x3c03b0:(250,246,250,360,182),0x3c03c0:(399,246,250,360,347),0x3c03d0:(250,246,399,360,244),0x3c03e0:(399,246,399,360,434),
        0x3c0430:(250,293,313,513,485),0x3c0440:(399,293,313,513,241),0x3c0310:(14,514,460,252,484),0x3c0300:(14,100,460,252,461)}
for off,(a,b_,c,d,spare) in arrays.items():
    assert bytes(b[off:off+16])==struct.pack('<IIII',a,b_,c,d), hex(off); b[off:off+16]=struct.pack('<IIII',spare,E,E,E)
for off in (0x2bec8c,0x2bee60,0x2bed71,0x2bef50):
    assert bytes(b[off:off+8])==bytes.fromhex('c74424308c000000'), hex(off); b[off+4]=E
open(sys.argv[2],'wb').write(b); print('ok md5', hashlib.md5(b).hexdigest())
