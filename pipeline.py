"""everydayhypehq daily carousel — orchestrator.
Run: python pipeline.py            (full: generate + publish)
     python pipeline.py --dry-run  (generate + render only, NO posting)
"""
import sys, json
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))
import config as C
from steps import s1_fetch_news, s2_brain, s3_gen_images, s4_render, s5_upload, s6_publish, hero, review

def run(dry_run=False):
    print("=== everydayhypehq carousel pipeline ===")
    cands = s1_fetch_news.fetch_candidates()
    plan  = s2_brain.make_plan(cands)
    if plan is None:
        print("No strong story today -> skipping (quality gate)."); return
    (C.WORK / "plan.json").write_text(json.dumps(plan, indent=2))

    bg_dir = s3_gen_images.generate(plan)

    # Person-centric story -> real license-free cut-out cover (Wikimedia photo + Wikidata logo).
    # Graceful: any failure -> hero_asset None -> normal FLUX cover.
    hero_asset = None
    if plan.get("person"):
        hero_asset = hero.build_hero(plan["person"], plan.get("company", ""), C.WORK / "hero")
        print(f"[hero] {plan['person']} / {plan.get('company','')} -> {'cut-out cover' if hero_asset else 'no free photo, FLUX cover'}")
        if hero_asset and hero_asset.get("credit"):
            plan["caption"] = (plan.get("caption", "") + f"\n\n\U0001F4F7 Cover photo: {hero_asset['credit']}").strip()

    slides = s4_render.render(plan, bg_dir, hero_asset)

    # Art-director QA agent: a vision model checks the carousel against brand rules before posting.
    verdict = review.review([str(p) for p in slides])
    (C.WORK / "review.json").write_text(json.dumps(verdict, indent=2))
    print(f"[review] verdict={verdict.get('verdict')} score={verdict.get('score')} issues={verdict.get('issues')}")

    if dry_run:
        print(f"[dry-run] slides ready in {slides[0].parent} — NOT posting."); return

    if verdict.get("verdict") == "skip":
        print("[review] ❌ art director rejected the carousel -> NOT posting today (quality gate)."); return

    urls = s5_upload.upload(slides)
    media_id = s6_publish.publish(urls, plan["caption"])
    s2_brain.commit_ledger(plan)          # only record after a successful post
    print(f"=== DONE — posted carousel {media_id} for '{plan['story']['title']}' ===")

if __name__ == "__main__":
    run(dry_run="--dry-run" in sys.argv)
