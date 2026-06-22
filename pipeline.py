"""everydayhypehq daily carousel — orchestrator.
Run: python pipeline.py            (full: generate + publish)
     python pipeline.py --dry-run  (generate + render only, NO posting)
"""
import sys, json
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))
import config as C
from steps import s1_fetch_news, s2_brain, s3_gen_images, s4_render, s5_upload, s6_publish, hero, review, telegram, pending

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

    paths = [str(p) for p in slides]
    cap = plan.get("caption", "")

    if dry_run:
        telegram.notify(paths, cap, verdict)   # preview to phone
        print(f"[dry-run] slides ready in {slides[0].parent} — NOT posting."); return

    if verdict.get("verdict") == "skip":
        telegram.notify(paths, cap, verdict)   # tell you it was skipped + why
        print("[review] ❌ art director rejected the carousel -> NOT posting today (quality gate)."); return

    # QUEUE FOR APPROVAL — don't post here. Upload now (so the agent can publish later with just
    # URLs), then DM the slides + Approve/Reject/Redo buttons. The agent (steps/agent.py) publishes
    # on your tap, applies any caption edits you reply with, or auto-posts after the deadline.
    urls = s5_upload.upload(slides)
    chat_id, ctrl_id = telegram.send_for_approval(paths, cap, verdict, C.APPROVAL_DEADLINE_MIN)
    if not ctrl_id:
        print("[pipeline] ⚠️ could not reach Telegram — NOT queuing (would never auto-resolve)."); return
    pending.create(cap, urls, plan, chat_id, ctrl_id, C.APPROVAL_DEADLINE_MIN)
    print(f"=== QUEUED for approval — '{plan['story']['title']}' "
          f"(auto-posts in ~{C.APPROVAL_DEADLINE_MIN//60}h if no response) ===")

if __name__ == "__main__":
    run(dry_run="--dry-run" in sys.argv)
