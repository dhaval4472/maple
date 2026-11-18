# Deployment notes for a small host

The site is intentionally cheap to host: no CDN, no external image service, no
video streaming, and no build tooling on the server.

## What actually gets uploaded

| Item | Approx. size |
| --- | --- |
| Application code, templates, config | under 1 MB |
| `static/` after the asset pass | ~6 MB |
| Python environment (Django + Pillow + gunicorn) | ~75–85 MB |
| SQLite database | under 1 MB |
| Uploaded damage photos | variable — budget ~0.2–0.5 MB per stored photo |

A fresh deployment is under 100 MB before user uploads. Keep the project under
that budget by excluding development-only folders.

For a fresh server, clone the repository:

```sh
sudo mkdir -p /srv/mapleleaf
sudo chown -R $USER:$USER /srv/mapleleaf
git clone https://github.com/dhaval4472/maple.git /srv/mapleleaf
```

For later updates, `rsync` with the provided exclude list also works:

```sh
rsync -av --exclude-from=.deployignore ./ user@host:/srv/mapleleaf/
```

`static/downloads/` holds the internal feature-roadmap PDF. It is not linked
from the public site, so it is excluded from deployment.

`source-assets/` contains the original hero video and original image files. It
is deliberately excluded from deployment. Do not copy the MP4s into `static/`;
the site paints a WebP frame sequence instead. This alone saves about 22 MB.

## Server setup

The project is Django-only; CSS and JavaScript are already built and committed,
so there is no npm or React build step on the server. Python, Django, Pillow and
Gunicorn all support ARM64, so Oracle's free Ampere instances work fine.

On Ubuntu 24.04 (ARM):

```sh
sudo apt update && sudo apt upgrade -y
sudo apt install -y python3 python3-venv python3-pip git nginx \
  build-essential libjpeg-dev zlib1g-dev libwebp-dev \
  certbot python3-certbot-nginx
```

Create the environment and install dependencies:

```sh
cd /srv/mapleleaf
python3 -m venv .venv
. .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

Create `/etc/mapleleaf.env` from `deploy/mapleleaf.env.example`. Fill in a fresh
`DJANGO_SECRET_KEY`, your real domain, and your server IP. Keep the file
root-owned with `600` permissions. The settings module reads these values at
startup; no source edits are needed on the server.

```sh
sudo cp deploy/mapleleaf.env.example /etc/mapleleaf.env
sudo chmod 600 /etc/mapleleaf.env
sudo nano /etc/mapleleaf.env
```

While obtaining the Let's Encrypt certificate, set
`DJANGO_SECURE_SSL_REDIRECT=0` and `DJANGO_SECURE_COOKIES=0`. Turn both on after
HTTPS works. `DJANGO_DEBUG=0` requires a real `DJANGO_SECRET_KEY`.

Prepare the database, collected static files, and upload folder:

```sh
cd /srv/mapleleaf
. .venv/bin/activate
set -a; . /etc/mapleleaf.env; set +a
python manage.py migrate
python manage.py collectstatic --noinput
python manage.py createsuperuser
mkdir -p media
```

Install the provided service and nginx templates:

```sh
sudo cp deploy/mapleleaf.service /etc/systemd/system/mapleleaf.service
sudo cp deploy/nginx-mapleleaf.conf /etc/nginx/sites-available/mapleleaf
sudo ln -s /etc/nginx/sites-available/mapleleaf /etc/nginx/sites-enabled/
# Edit the service user if the host is Oracle Linux (use opc instead of ubuntu).
# Replace the placeholder domain names in the nginx file.
sudo nginx -t
sudo systemctl daemon-reload
sudo systemctl enable --now mapleleaf
sudo systemctl restart nginx
sudo certbot --nginx -d your-domain.com -d www.your-domain.com
```

Open ports **80** and **443** in both the Oracle VCN security list and the
instance firewall. nginx serves `/static/` and `/media/`; Gunicorn serves the
Django app on `127.0.0.1:8000`. One worker with four threads keeps the in-memory
sign-in rate limit consistent on this small site.

The site timezone is `America/Winnipeg`. Keep regular off-server backups of
`db.sqlite3` and `media/`; Oracle may reclaim an idle free-tier instance.

## Staff workspace

The shop manages day-to-day work from the website at:

```
https://your-domain.example/staff/
```

The public header and footer have one **Login** link. There is no separate
customer or staff button and no public sign-up. Everyone uses the same form at:

```
https://your-domain.example/login/
```

After authenticating, the account decides where the person lands:

| Account | Destination |
| --- | --- |
| **Master** (shop owner) | Staff dashboard at `/staff/` |
| **Employee** | My work at `/staff/my-work/` |
| **Customer** | Customer account at `/account/` |
| **No account area** | A generic "no access" message; nobody has to choose a role |

The older `/staff/login/` and `/account/login/` pages still work for bookmarks
and links, but the public site no longer needs them. There are two staff
account roles:

| Role | Can open |
| --- | --- |
| **Master** (shop owner) | Dashboard, work tickets, team, customers, request inbox, reviews, repair stories, blog, website activity, stockroom (parts, reorder list, suppliers), import/export and My account |
| **Employee** | My work, Find a part (search only, no costs or stock administration) and My account |

The role is stored in `StaffProfile`, not in Django's `is_staff` flag. A
superuser or any existing Django staff account is treated as a master, so the
original owner login keeps working after the upgrade. Employee accounts are
ordinary user accounts and cannot open `/admin/`.

What the master area covers:

- **Dashboard** — new requests, upcoming drop-off requests, a 7-day summary and
  a shop-floor panel showing assigned, in-progress, completed-this-week and
  overdue work.
- **Work tickets** — assign a job to one employee, optionally link it to a
  booking, set a due date and instructions, then track it from Assigned to
  In progress to Completed. The master can cancel or reopen a ticket and can
  reassign active work.
- **Team** — create employee accounts, edit names/contact details, reset
  passwords and deactivate or reactivate sign-in. Employees never get Django
  staff or admin access.
- **Customers** — create shop-managed customer accounts, edit contact details,
  reset passwords and deactivate/reactivate sign-in. Matching requests are
  linked by email or phone; customers see only their own public request status.
- **Request inbox** — callbacks, bookings, MPI claim intakes and photo requests,
  with search, status filters, CSV export, status updates, private notes, photo
  viewing/deletion and permanent deletion.
- **Reviews** — add, edit, publish/hide and delete real customer reviews.
- **Repair stories** — add/edit before-and-after stories with automatic WebP
  optimisation. A story is public only when both written customer permission
  and the publish box are set.
- **Blog** — write Markdown articles, manage categories and tags, run the SEO
  publish gate, preview drafts and moderate comments. Only the master can open
  these pages.
- **Website activity** — first-party page views and events, with a CSV export.
- **Stockroom** — parts catalogue, suppliers, receive/use/count/adjust, a low-stock
  reorder list, CSV import/export and the parts cost on each work ticket.
- **My account** — update your name/email/phone, change your password and sign
  out.

### Work ticket rules

- A ticket can be created from scratch under **Work tickets**, or from a
  booking's detail page with **Create work ticket**. The form prefills the
  customer, vehicle and requested service, and keeps the booking linked.
- The assigned employee sees the vehicle, work type, instructions, customer
  name/phone and the customer's original booking notes. Internal request notes
  are never shown to employees.
- The employee presses **Start working**, can save work notes, then presses
  **Mark complete**. Start and completion times are recorded.
- Active tickets can be edited or reassigned. Reassigning resets the ticket to
  Assigned and clears the start/finish times.
- Completed and cancelled tickets must be reopened before they can be edited;
  reopening also resets them to Assigned.
- An employee cannot be deactivated while they still have open tickets.
  Reassign or finish those tickets first.
- There are no email or SMS notifications. New assignments appear as a sidebar
  badge and on the employee's **My work** page.

### Stockroom rules

Open **Stockroom → Parts** to search the catalogue and see what is on the shelf.

- Stock is a whole number. Paint, fluids and other containers are counted as the
  container the shop actually buys, such as a quart or a gallon.
- `Part.quantity_on_hand` is a cached balance. It only changes through a stock
  movement, so the ledger and the shelf count always have an explanation.
- **Receive stock** raises the balance for a delivery and can update the unit
  cost. The supplier delivery sheet receives several parts at once.
- **Use stock** lowers the balance. A master can link it to any ticket; an
  employee can link it only to their own open ticket. Employees never see unit
  costs, stock value, supplier pricing or the master's stock screens.
- **Count stock** records the number actually counted. If it matches, only the
  last-counted date changes. If it differs, the difference is saved as a movement
  with the chosen reason.
- **Adjust stock** is for damage, shrinkage, a supplier return or a correction.
  A reason is required and the change is added to the ledger.
- A part appears on the **Reorder list** when it is active, its reorder level is
  above zero, and the quantity on hand is at or below that level. The suggested
  order is the restock target minus the quantity on hand, with a minimum of one.
  Critical parts are pinned first.
- Parts and suppliers are archived, not deleted. Their movements and past ticket
  costs stay in place. `StockMovement.part` uses `PROTECT`.
- A master can return part of a ticket's stock. The return creates a new
  movement; earlier movements are never edited or deleted.

### Daily stock routine

A simple routine is enough to keep the shelf honest:

1. When a delivery arrives, open **Reorder list → Receive delivery** for that
   supplier and enter the quantities that actually arrived.
2. When a part leaves the shelf, open the part and choose **Use stock**. On a job,
   link it to the ticket so the parts and cost show on that job.
3. Once a week, open the **Reorder list** and call or email the supplier for
   anything at or below its level. The **Copy list** button copies a plain-text
   order for the supplier group.
4. Once a month, **Count stock** for the parts the shop uses most. Use **Adjust**
   only for a known correction, never as a shortcut for a count.
5. If a balance ever looks wrong and the history cannot explain it, run the
   ledger repair command on the host:

```sh
python manage.py rebuild_stock --dry-run
python manage.py rebuild_stock
```

The first command shows what would change. The second recalculates each cached
balance from its movements. It does not create or delete movements.

### CSV import and export

- Use **Stockroom → Parts → Import** to load a spreadsheet. Only `sku` and `name`
  are required; the download template has every supported column.
- Existing SKUs are matched and updated. Their current stock is never replaced
  by the file.
- Opening stock is applied only to brand-new parts, as a `count` movement. This
  keeps the ledger complete from the first day.
- Bad rows are listed before anything is saved. Suppliers named in the file can
  be created automatically, or rejected if the box is unticked.
- **Export current parts** and the reorder-list CSV are master-only downloads.

Django admin remains available at `/admin/` for masters as a secondary tool for
low-level settings. The staff area is the intended day-to-day interface.

### Creating the first owner account

Run this once on the server:

```sh
cd /srv/mapleleaf
. .venv/bin/activate
python manage.py createsuperuser
```

Use a unique username and a long password. The account is a superuser and is
treated as a master, so it can open both `/staff/` and `/admin/`. Do not put the
password in the repository, a template, or an email that is kept indefinitely.

### Creating employee accounts

Sign in as a master, open **Team**, then choose **Add employee**. Set the
username, the employee's name, optional email and phone, and a temporary
password. Share those details with the employee directly — the site does not
send account email. The employee can change the password under **My account**.

No public sign-up exists. The Team page and `createsuperuser` are the only ways
to create workspace accounts.

### Resetting a forgotten password

A master can reset an employee's password from **Team** → **Password**. For the
master account itself, run this on the server with the username:

```sh
python manage.py changepassword <username>
```

The command prompts for a new password twice. Any signed-in user can also change
their own password inside `/staff/account/password/`.

### Repair estimator pricing

The public estimator lives at `/tools/repair-estimate/`. It is a planning
range, never a quote, and it can only show numbers a master has entered.

- Open **Staff → Pricing → Estimator** to see every public service.
- Services are seeded with no price and switched off. A card shows **Call for
  pricing** until a master enters a base price and ticks **Show this price on
  the public estimator**.
- **Settings** holds the master switch, the rounding step, the vehicle
  multipliers (car, SUV, luxury), the severity multipliers (minor, moderate,
  severe) and the disclaimer shown with every range.
- The range is built from the base price ± the spread, then multiplied by the
  vehicle adjustment and, when the service asks about damage severity, the
  severity adjustment. Enabled add-ons are added to both ends. The low end is
  rounded down and the high end up, using the chosen step.
- A service with **Ask about damage severity** ticked shows a minor / moderate /
  severe choice. Leave it off for fixed-scope work such as oil changes.
- When a visitor chooses **Insurance or MPI claim**, the shop range is skipped
  entirely and the page sends them to the MPI claim navigator. MPI settles
  coverage; the estimator does not guess at it.
- The public tool is anonymous and writes nothing to the database. It has a
  honeypot and a cache-based rate limit, and the optional follow-up uses the
  existing callback request rather than a new storage table.
- Turning the master switch off leaves the page online but replaces every range
  with a **call for pricing** message, so stale numbers are never published.
- Set **Prices last reviewed** so visitors can see how current the guide is,
  and keep the disclaimer wording that says it is not a quote.
- Employees cannot open the estimator pages; they are master-only. Django admin
  remains available at `/admin/` as a secondary editor for the same rows.

### Blog and SEO

The public blog lives at `/blog/`. Articles, categories, tags and comments are
managed only under **Staff → Blog**; employees cannot open any blog page. The
body is Markdown only — headings use `##`, links are relative (for example
`/services/windshield/`), and raw HTML is removed when the page renders. The
rendering libraries (`markdown-it-py` and `bleach`) are pinned in
`requirements.txt`, so there is no extra server setup.

**Writing and publishing**

- Start with **Write article**. Save draft keeps the post private; **Check &
  publish** runs the same gate shown in the live panel on the edit screen.
- **Preview** opens the draft in the public template with `noindex, nofollow`.
  Only a master can use it or see the draft; visitors get a 404.
- Featured images are re-encoded as WebP and require alt text. The image and
  article text are stored in `media/` and `db.sqlite3`, so include both in
  backups.
- Categories group articles; tags connect them across categories. New tags can
  be typed into the article editor with commas, or created under **Categories &
  tags**.
- Published posts, non-empty categories and non-empty tags are added to
  `/sitemap.xml` automatically. Drafts and empty topic pages are excluded.
- Article pages include a canonical URL, Open Graph tags and JSON-LD
  (`BlogPosting` and breadcrumbs). Keep `DJANGO_ALLOWED_HOSTS` set to the real
  domain so generated canonical URLs match the public address.

**The publish gate**

Google has no official pass/fail API, so this is a best-practice checklist, not
a ranking guarantee. Required checks block publishing: unique title and slug;
SEO title of 30–60 characters; meta description of 120–160 characters (the
excerpt is the fallback); a focus keyword used in the title, slug and opening
paragraph; at least 300 words; at least one H2; a relative link to a service,
tool or blog page; alt text when an image is used; and a keyword-stuffing limit.
Advisory checks — featured image, FAQ section, short paragraphs and an external
citation — are reminders only and never block a publish.

Editing a live post so it fails a required check returns it to drafts instead
of leaving stale SEO metadata online. Fix the highlighted items and publish
again.

**Comments**

Comments need a name and a message only — no login, email field or account.
They publish instantly after honeypot, length, link-count, duplicate,
repeated-character, spam-phrase and uppercase-ratio checks, plus a limit of five
comments per article per IP in ten minutes. Rendered links use
`rel="nofollow noopener"`. Masters can hide or delete anything from **Blog →
Comments**. Nothing is emailed or texted when a comment arrives.

Customers sign in through the same page as everyone else:

```
https://your-domain.example/login/
```

`/account/` remains the customer dashboard and `/account/login/` remains
available for old links. There is no public sign-up. A master creates the
account from **Customers** in the staff workspace, then shares the username and
temporary password directly. The customer can change the password after signing
in.

- The **Customers** page lists active and deactivated customer accounts, with
  the number of linked requests, password reset and deactivate/reactivate
  controls.
- When an account is created or its email/phone changes, the site links
  unclaimed requests that match the same email address or phone number. The
  match ignores formatting in phone numbers.
- If a signed-in customer submits a new booking, callback, MPI claim or photo
  request with the same email or phone as their account, it is linked
  automatically. A request submitted for someone else stays unlinked.
- A customer sees only their own request references, type, public status and the
  details they submitted. Internal notes, employee notes, costs, stock and other
  customers' requests are never included.
- Customer pages are `noindex, nofollow` and use the same 8-failed-attempts-per-
  15-minutes sign-in limit as the staff workspace.
- Deactivating a customer account blocks sign-in but keeps the request links, so
  the history returns if the account is reactivated.

Customer accounts live in `CustomerProfile`. They are separate from
`StaffProfile`, so a customer can never open `/staff/` and an employee cannot
open `/account/`.

### Staff-area security notes

- Every `/staff/` view requires an active account with a master or employee
  role. Anonymous visitors are redirected to the sign-in page; accounts without
  a role are rejected and cannot sign in.
- Master-only pages redirect employees back to **My work**. Employee pages are
  also protected by server-side ownership checks, so an employee cannot open or
  change another employee's ticket by guessing its URL.
- The workspace and sign-in pages send `noindex, nofollow`.
- Sign-in is rate limited to 8 failed attempts per IP address per 15 minutes.
  All sign-in pages share the same counter, so opening a different page does not
  reset the limit. The counter uses Django's cache; on a multi-process host,
  configure a shared cache backend if you want the limit shared across workers.
- If the app runs behind nginx or another trusted proxy, set
  `TRUST_X_FORWARDED_FOR=1` so the real client address is used. Leave it off
  when the app is reachable directly, because the header can be spoofed.
- Staff pages are marked private by authentication, not by obscurity. Use HTTPS
  in production so passwords and customer details are encrypted in transit.
- Employees are not Django staff, so `/admin/` stays blocked for them. Only give
  Django staff or superuser status to someone who genuinely needs admin access.
- Uploaded damage photos and repair-story images live in `media/`. Keep that
  folder out of public directory listings and include it in backups.
- Deleting a request or story from the staff area also deletes its image files.
  Export a CSV first if the shop needs a record.

### Front-end assets

`static/css/app.css` is generated from `static/css/input.css`. After changing
staff, customer or public styles, rebuild and bump the `?v=` query string in
`templates/mapleleaf/base.html`, `templates/staff/base.html`,
`templates/staff/login.html`, `templates/customer/base.html`,
`templates/customer/login.html` and `templates/auth/login.html`:

```sh
npm install
npm run build:css
```

`static/js/staff.js` handles the mobile sidebar, confirmation prompts, flash
messages, password reveal and the reorder-list copy button. Keep it deployed
with the templates.

## Email notifications

Callback, booking, claim and photo-request notifications are saved in the admin
immediately. Email delivery is separate: without SMTP settings the site uses
Django's console backend, so messages are only printed in the server log.

Set these environment variables on the host to enable real delivery:

```sh
EMAIL_HOST=smtp.example.com
EMAIL_PORT=587
EMAIL_HOST_USER=website@example.com
EMAIL_HOST_PASSWORD=...
EMAIL_USE_TLS=1
EMAIL_USE_SSL=0
```

`SHOP_EMAIL` in `config/settings.py` is the recipient. If the mail server
rejects a message, the request is still stored and the error is written to the
application log.


## Rebuilding large assets

These commands run on a development machine, not on the host. They require
`requirements-dev.txt` (OpenCV is only used for frame extraction).

```sh
python scripts/build_hero_frames.py
python scripts/optimize_static_images.py
```

The hero film is 60 frames at 1280×720 (desktop) and 960×540 (mobile), about
4.9 MB total. If you increase `--frames`, also update `data-frame-count` in
`templates/mapleleaf/home.html` and bump `data-frame-version` so browsers fetch
the new sequence.

Reference the generated `.webp` images in templates. Original PNG/JPG sources
are archived in `source-assets/img-original/` and are not deployed.

## Keeping uploads small

Damage photos are automatically:

- rotated according to EXIF orientation,
- stripped of metadata,
- resized to a maximum of 1600 px,
- re-encoded as WebP at quality 82.

The form accepts up to 4 photos, 6 MB each. A typical stored photo is a few
hundred KB, so a photo request is usually around 1 MB or less.

Repair-story before/after images uploaded in the staff area are prepared the
same way, with a larger 1800 px limit and WebP quality 84 because they appear
at gallery size. Both limits are configurable in `mapleleaf_app/forms.py`
(public photos) and `mapleleaf_app/staff_forms.py` (stories).

## Retention and cleanup

The default retention period is 365 days (`PHOTO_RETENTION_DAYS`). Review this
with the shop: 90–180 days is easier on a small disk and still enough time to
finish an estimate.

Cleanup runs automatically once per day when someone submits a photo request.
For a guaranteed daily sweep, add a cron job:

```cron
15 3 * * * cd /srv/mapleleaf && .venv/bin/python manage.py prune_photo_requests >> /var/log/mapleleaf-prune.log 2>&1
```

Check the footprint at any time:

```sh
python manage.py storage_report
```

## Backups

The database and media folder are the only things that cannot be regenerated.
The stock ledger, cached balances, tickets and customer records all live in the
database, so one database backup covers them. Back them up together, for example:

```sh
python manage.py dumpdata --natural-foreign --natural-primary -e contenttypes -e auth.Permission > backup.json
tar czf media-$(date +%F).tar.gz media/
```

Keep backups off the host. Static assets and the virtual environment can be
rebuilt from the repository and `requirements.txt`.
