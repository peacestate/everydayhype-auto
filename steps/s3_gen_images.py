"""Step 3 — generate the 5 backgrounds on Kaggle (FLUX.1-schnell 4-bit, proven working).
Injects the brain's prompts + art-style into the kernel, pushes to the IMAGE account, polls, pulls.
Auth in CI via KAGGLE_USERNAME/KAGGLE_KEY env (set as GitHub Secrets)."""
import json, time, subprocess, shutil, os
from pathlib import Path
import config as C

KDIR = C.WORK / "kernel"
BG   = C.WORK / "bg"

KERNEL_TMPL = r'''import os, sys, subprocess, numpy as np
def pip(*a):
    # check=True on purpose: a SILENT pip failure is what broke 2026-08-13. The old
    # torch==2.4.1 pin stopped resolving (nvidia-cudnn-cu12==9.1.0.70 vanished from the
    # index), pip exited non-zero, check=False swallowed it, and the run limped on with
    # stock torch — which no longer supports the P100. Fail loud instead.
    subprocess.run([sys.executable,"-m","pip","install","-q",*a], check=True)
# NO torch pin any more. We now request a T4 (sm_75, see machine_shape below) instead of
# the P100 (sm_60), which Kaggle's stock torch dropped support for — so the stock build
# works as-is and there is no pin left to rot.
pip("diffusers==0.32.2","transformers==4.46.3","accelerate","sentencepiece","protobuf","bitsandbytes")
import torch
cap = torch.cuda.get_device_capability(0)
print("[gpu]", torch.cuda.get_device_name(0), cap, "torch", torch.__version__, flush=True)
assert cap >= (7,5), f"got {torch.cuda.get_device_name(0)} {cap}; need sm_75+ (T4) for bitsandbytes 4-bit"
from huggingface_hub import login; login(token=%(hf)r)
from diffusers import FluxPipeline, FluxTransformer2DModel, BitsAndBytesConfig as DBnb
from transformers import T5EncoderModel, BitsAndBytesConfig as TBnb
repo="black-forest-labs/FLUX.1-schnell"; nf4=dict(load_in_4bit=True,bnb_4bit_quant_type="nf4",bnb_4bit_compute_dtype=torch.float16)
tf=FluxTransformer2DModel.from_pretrained(repo,subfolder="transformer",quantization_config=DBnb(**nf4),torch_dtype=torch.float16)
te=T5EncoderModel.from_pretrained(repo,subfolder="text_encoder_2",quantization_config=TBnb(**nf4),torch_dtype=torch.float16)
pipe=FluxPipeline.from_pretrained(repo,transformer=tf,text_encoder_2=te,torch_dtype=torch.float16); pipe.enable_model_cpu_offload()
STYLE=%(style)r
PROMPTS=%(prompts)r
for k,p in PROMPTS.items():
    img=pipe(p+STYLE,num_inference_steps=4,guidance_scale=0.0,height=1280,width=1024,max_sequence_length=256,
             generator=torch.Generator("cpu").manual_seed(1000+int(k))).images[0]
    img.save(f"/kaggle/working/{k}.png"); print("DONE",k,"meanpix",round(float(np.asarray(img).mean()),1),flush=True)
print("ALL DONE",flush=True)
'''

def _kaggle(*args):
    env = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
    r = subprocess.run(["kaggle", *args], capture_output=True, text=True, env=env)
    if r.returncode != 0:
        raise RuntimeError(f"kaggle {' '.join(args)} failed (rc={r.returncode}): {r.stderr.strip()}")
    return r.stdout

def generate(plan):
    if shutil.rmtree(BG, ignore_errors=True) or True: BG.mkdir(parents=True, exist_ok=True)
    KDIR.mkdir(parents=True, exist_ok=True)
    style = f", {plan['art_style']}, dark cinematic, the lower third darker and emptier with space for text, absolutely no text, no letters, no numbers, no charts, no graphs, no logos, no UI screens, no signage, no watermark"
    prompts = {str(i+1): s["image_prompt"] for i, s in enumerate(plan["slides"])}
    (KDIR/"gen_flux.py").write_text(KERNEL_TMPL % {"hf": C.HF_TOKEN, "style": style, "prompts": prompts})
    (KDIR/"kernel-metadata.json").write_text(json.dumps({
        "id": C.KAGGLE_KERNEL, "title": C.KAGGLE_KERNEL.split("/")[1], "code_file": "gen_flux.py",
        "language": "python", "kernel_type": "script", "is_private": True,
        # machine_shape pins the accelerator. "NvidiaTeslaP100" (what plain enable_gpu gives
        # you) is sm_60, which Kaggle's stock torch no longer builds for -> bitsandbytes dies
        # with "Error named symbol not found ... ops.cu". T4 is sm_75, same 16GB, fully
        # supported. Allowed values: NvidiaTeslaT4 | NvidiaTeslaP100 | Tpu1VmV38.
        "enable_gpu": True, "machine_shape": "NvidiaTeslaT4", "enable_internet": True,
        "dataset_sources": [], "competition_sources": [], "kernel_sources": [], "model_sources": []}))

    print("[s3] pushing FLUX kernel...", flush=True)
    print(_kaggle("kernels", "push", "-p", str(KDIR)), flush=True)
    # poll — cold start (pip installs + full FLUX weight download) can run long on Kaggle's
    # free GPU queue, so give it generous headroom (100 min) rather than the old 60.
    for _ in range(100):
        time.sleep(60)
        st = _kaggle("kernels", "status", C.KAGGLE_KERNEL)
        print("[s3]", st.strip(), flush=True)
        if "COMPLETE" in st: break
        if "ERROR" in st: raise RuntimeError("FLUX kernel ERROR:\n" + st)
    else:
        raise TimeoutError("FLUX kernel timed out")
    print(_kaggle("kernels", "output", C.KAGGLE_KERNEL, "-p", str(BG)))
    imgs = sorted(BG.glob("*.png"))
    assert len(imgs) >= 5, f"expected 5 bg images, got {len(imgs)}"
    print(f"[s3] pulled {len(imgs)} backgrounds")
    return BG
