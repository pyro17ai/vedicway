export async function prepareCarousel(page, payload) {
  const profileUrl = `https://www.tiktok.com/${payload.account}`;
  const studioUrl = 'https://www.tiktok.com/tiktokstudio/upload?tab=photo';
  const resuming = payload.resumeCurrent === true
    && page.url().includes('/tiktokstudio/upload/post/photo');

  if (!resuming) {
    await page.goto(profileUrl, { waitUntil: 'domcontentloaded', timeout: 45_000 });
    await page.waitForTimeout(2_000);
    const editProfile = page.getByRole('button', {
      name: /Edit profile|Редактировать профиль/i,
    });
    const ownProfileLink = page.locator(`a[href="/${payload.account}"]`).first();
    try {
      await Promise.race([
        editProfile.waitFor({ state: 'visible', timeout: 30_000 }),
        ownProfileLink.waitFor({ state: 'visible', timeout: 30_000 }),
      ]);
    } catch {
      // The explicit account check below emits the stable runner error.
    }
    const ownsProfile = await editProfile.isVisible().catch(() => false)
      || await ownProfileLink.isVisible().catch(() => false);
    if (!page.url().includes(`/${payload.account}`) || !ownsProfile) {
      throw new Error(`TikTok account mismatch: expected ${payload.account}`);
    }
    await page.goto(studioUrl, { waitUntil: 'domcontentloaded', timeout: 45_000 });
    await page.waitForTimeout(4_000);
    const unsavedDraft = page.getByText(/unsaved photo post|несохранённ.*фотопубликац/i);
    if (await unsavedDraft.count()) {
      throw new Error('TikTok Studio already contains an unrelated unsaved photo draft');
    }
    const photosTab = page.getByRole('tab', { name: /Photos|Фото/i });
    if (await photosTab.isVisible()) await photosTab.click();
    const input = page.locator('input[type="file"]').first();
    await input.setInputFiles(payload.slides);
  }

  const uploaded = page.getByText(/6 photos uploaded|загружено 6 фото/i).first();
  await uploaded.waitFor({ state: 'visible', timeout: 120_000 });
  const titleInput = page.getByPlaceholder(/Add a catchy title|Добавьте.*заголовок/i);
  const descriptionInput = page.locator('[contenteditable="true"][role="combobox"]').first();
  if (await titleInput.inputValue() !== payload.title) await titleInput.fill(payload.title);
  if (await descriptionInput.innerText() !== payload.description) {
    await descriptionInput.fill('');
    await descriptionInput.fill(payload.description);
  }
  if (await titleInput.inputValue() !== payload.title) throw new Error('TikTok title did not persist');
  if (await descriptionInput.innerText() !== payload.description) throw new Error('TikTok description did not persist');

  const replaceSound = page.getByText(/^(Replace|Заменить)$/i).first();
  let sound = null;
  if (!await replaceSound.isVisible().catch(() => false)) {
    await page.getByRole('button', { name: /^(Add sound|Добавить звук)$/i }).click();
    const soundSearch = page.getByRole('textbox', { name: /Search sounds|Поиск звуков/i });
    await soundSearch.waitFor({ state: 'visible', timeout: 30_000 });
    await soundSearch.fill('ambient');
    await soundSearch.press('Enter');
    await page.waitForTimeout(2_000);
    const soundResults = page.getByRole('listitem').filter({
      has: page.getByRole('button', { name: /^(Use|Использовать)$/i }),
    });
    await soundResults.first().waitFor({ state: 'visible', timeout: 30_000 });
    const soundCount = await soundResults.count();
    const soundResult = soundResults.nth(Math.floor(Math.random() * soundCount));
    sound = (await soundResult.innerText()).split('\n')[0].trim();
    await soundResult.getByRole('button', { name: /^(Use|Использовать)$/i }).click();
    await replaceSound.waitFor({ state: 'visible', timeout: 30_000 });
  }

  const comboboxValues = await page.getByRole('combobox').allTextContents();
  const visibleEveryone = await page.getByText(/^(Everyone|Все)$/i).first()
    .isVisible()
    .catch(() => false);
  if (!visibleEveryone
    && !comboboxValues.some((value) => /^(Everyone|Все)$/i.test(value.trim()))) {
    throw new Error('TikTok visibility is not Everyone');
  }
  const now = page.getByRole('radio', { name: /Now|Сейчас/i });
  if (!await now.isChecked()) throw new Error('TikTok is not set to post now');
  const postButton = page.getByRole('button', { name: 'Post', exact: true });
  if (!await postButton.isEnabled()) throw new Error('TikTok Post button is disabled');

  await page.screenshot({ path: payload.evidencePath, fullPage: true });
  return {
    status: 'prepared',
    account: payload.account,
    studio_url: page.url(),
    sound,
    evidence_path: payload.evidencePath,
  };
}

export async function publishPreparedCarousel(page, payload) {
  const postButton = page.getByRole('button', { name: 'Post', exact: true });
  if (!await postButton.isEnabled()) throw new Error('TikTok Post button is disabled before click');
  const clickedAfter = Math.floor(Date.now() / 1000) - 300;
  await postButton.click();

  let acknowledged = false;
  for (let attempt = 0; attempt < 45 && !acknowledged; attempt += 1) {
    const acknowledgement = page.getByText(/published|posting|processing|uploaded to TikTok|опубликован|публикуется|загружен/i);
    acknowledged = !page.url().includes('/tiktokstudio/upload/post/photo')
      || await acknowledgement.count() > 0;
    if (!acknowledged) await page.waitForTimeout(2_000);
  }
  if (!acknowledged) throw new Error('TikTok did not confirm the single Post click');

  const verificationPage = await page.context().newPage();
  let postUrl = null;
  try {
    const matchingItems = [];
    const captureItems = async (response) => {
      if (!response.url().includes('/tiktok/creator/manage/item_list/v1/')) return;
      if (!response.ok()) return;
      try {
        const body = await response.json();
        for (const item of body.item_list || []) {
          if (item.desc === payload.description && Number(item.create_time) >= clickedAfter) {
            matchingItems.push(item);
          }
        }
      } catch {
        // A later Studio poll can still return a valid JSON response.
      }
    };
    verificationPage.on('response', captureItems);
    for (let attempt = 0; attempt < 12 && !postUrl; attempt += 1) {
      await verificationPage.goto('https://www.tiktok.com/tiktokstudio', {
        waitUntil: 'domcontentloaded',
        timeout: 45_000,
      });
      await verificationPage.waitForTimeout?.(3_000);
      const item = matchingItems
        .filter((candidate) => /^\d+$/.test(String(candidate.item_id || '')))
        .sort((left, right) => Number(right.create_time) - Number(left.create_time))[0];
      if (item) postUrl = `https://www.tiktok.com/${payload.account}/photo/${item.item_id}`;
      if (!postUrl && attempt < 11) await page.waitForTimeout(5_000);
    }
    if (!new RegExp(`^https://www\\.tiktok\\.com/${payload.account}/(?:photo|video)/\\d+`).test(postUrl ?? '')) {
      throw new Error('TikTok Studio did not expose a verified new post URL');
    }
    await verificationPage.screenshot({ path: payload.evidencePath, fullPage: true });
  } finally {
    await verificationPage.close();
  }
  return { status: 'published', post_url: postUrl, evidence_path: payload.evidencePath };
}
