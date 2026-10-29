#!/usr/bin/env python3
"""Накладає українські/російські тексти з translations_uk_ru.json на ВАШ LocalString.dat по ID.
Нічого не додає і не видаляє (кількість записів — зашита в WellPrint), міняє лише тексти в тегах <Ukrainian> і <Russian>.
Використання:  python3 apply-translations.py "C:\\WellPrint\\AssemblyData\\Fixed\\LocalString.dat"
Робить бекап LocalString.dat.bak, зберігає UTF-8 з BOM і CRLF, перевіряє, що XML валідний і кількість записів не змінилась."""
import sys, re, json, os, shutil, xml.etree.ElementTree as ET
if len(sys.argv) < 2: sys.exit(__doc__)
path = sys.argv[1]
tr = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'translations_uk_ru.json'), encoding='utf-8'))
raw = open(path, 'rb').read()
bom = raw.startswith(b'\xef\xbb\xbf'); s = raw.decode('utf-8-sig')
before = len(re.findall(r'<SubItem>', s)); changed = 0
def set_lang(item, lang, val):
    if re.search(rf'<{lang}\s*/>', item): return re.sub(rf'<{lang}\s*/>', f'<{lang}>{val}</{lang}>', item)
    return re.sub(rf'(<{lang}>)[^<]*(</{lang}>)', lambda m: m.group(1)+val+m.group(2), item)
def repl(m):
    global changed
    item = m.group(0); rid = re.search(r'<StringResourceId>([^<]*)</StringResourceId>', item).group(1)
    if rid not in tr: return item
    new = set_lang(set_lang(item, 'Ukrainian', tr[rid]['uk']), 'Russian', tr[rid]['ru'])
    if new != item: changed += 1
    return new
s2 = re.sub(r'<SubItem>[\s\S]*?</SubItem>', repl, s)
assert len(re.findall(r'<SubItem>', s2)) == before, 'кількість записів змінилась — не зберігаю'
ET.fromstring(s2.encode('utf-8'))  # валідність XML
shutil.copy2(path, path + '.bak')
open(path, 'wb').write(b'\xef\xbb\xbf' + s2.encode('utf-8'))
print(f'OK: записів {before}, оновлено {changed}, бекап {path}.bak')
