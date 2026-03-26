# 💰 Ad Setup Guide — PlaylistGrabber

## Why NOT Google AdSense?

Google owns YouTube. A site that downloads YouTube videos violates both YouTube's TOS
and Google AdSense policies. Your account **will** be banned. Use alternative ad networks instead.

---

## Recommended: Adsterra

**Website:** https://www.adsterra.com  
**Minimum Payout:** $5  
**Payment Methods:** PayPal, Paxum, WebMoney, Wire Transfer, Bitcoin  

### Step 1 — Sign Up

1. Go to https://publishers.adsterra.com/signup
2. Register as a **Publisher**
3. Add your domain (your Render URL or custom domain)
4. Wait for approval (usually 1-24 hours)

### Step 2 — Create Ad Units

Once approved, go to **Websites → Ad Units** and create these:

| Ad Type         | Size     | Where to Place               |
|-----------------|----------|-------------------------------|
| Banner          | 728×90   | Top of page (above input)     |
| Banner          | 728×90   | Bottom of page                |
| Social Bar      | Auto     | Floating bar (high revenue)   |
| Native Banner   | Auto     | Between video items           |

### Step 3 — Paste Code in index.html

Open `templates/index.html` and find the ad slot placeholders:

#### Top Banner
Find this in the HTML:
```html
<div class="ad-slot" id="adSlotTop">
    <!-- ADSTERRA: Paste your 728x90 banner code here -->
    <span class="ad-slot-id">Ad Space — Top Banner</span>
</div>
```

**Replace** the inner content with your Adsterra banner code:
```html
<div class="ad-slot" id="adSlotTop">
    <script async src="//YOUR_ADSTERRA_SCRIPT.js"></script>
</div>
```

#### Bottom Banner
Same process for `adSlotBottom`.

#### Social Bar (Optional — Highest Revenue)
Paste the Social Bar script just before `</body>`:
```html
<script async src="//YOUR_SOCIAL_BAR_SCRIPT.js"></script>
</body>
```

---

## Alternative Ad Networks

| Network       | Min Payout | Notes                           |
|---------------|------------|---------------------------------|
| Monetag       | $5         | By PropellerAds team, easy setup|
| HilltopAds    | $20        | Accepts download sites          |
| Adcash        | $25        | Good global rates               |
| A-Ads         | ~$0 (BTC)  | Crypto ads, zero restrictions   |
| ExoClick      | $20        | Very permissive policies        |

---

## Revenue Tips

1. **Social Bar** ads have the best CPM for tool sites (usually $1-4 CPM)
2. **Popunder** ads pay well but annoy users — use sparingly
3. **Native banners** between video items get good click-through rates
4. Add a **"Premium / No Ads"** option later via Stripe for extra revenue
5. Focus on driving traffic via SEO (target keywords like "download youtube playlist")
