"""everydayhypehq daily carousel — orchestrator.
Run: python pipeline.py            (full: generate + publish)
     python pipeline.py --dry-run  (generate + render only, NO posting)
"""
import sys, json
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))
import config as C
from steps import s1_fetch_news, s2_brain, s3_gen_images, s4_render, s5_upload, s6_publish

def run(dry_run=False):
    print("=== everydayhypehq carousel pipeline ===")
    cands = s1_fetch_news.fetch_candidates()
    plan  = s2_brain.make_plan(cands)
    if plan is None:
        print("No strong story today -> skipping (quality gate)."); return
    (C.WORK / "plan.json").write_text(json.dumps(plan, indent=2))

    bg_dir = s3_gen_images.generate(plan)
    slides = s4_render.render(plan, bg_dir)

    if dry_run:
        print(f"[dry-run] slides ready in {slides[0].parent} — NOT posting."); return

    urls = s5_upload.upload(slides)
    media_id = s6_publish.publish(urls, plan["caption"])
    s2_brain.commit_ledger(plan)          # only record after a successful post
    print(f"=== DONE — posted carousel {media_id} for '{plan['story']['title']}' ===")

if __name__ == "__main__":
    run(dry_run="--dry-run" in sys.argv)
