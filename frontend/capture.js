const puppeteer = require('puppeteer');

(async () => {
  const browser = await puppeteer.launch({
    headless: "new",
    args: ['--no-sandbox', '--disable-setuid-sandbox']
  });
  const page = await browser.newPage();
  
  page.on('console', msg => console.log('PAGE LOG:', msg.text()));
  page.on('pageerror', error => console.log('PAGE ERROR:', error.message));

  await page.setViewport({ width: 1280, height: 800 });
  await page.goto('http://localhost:3000', { waitUntil: 'networkidle0' });
  
  // Set localStorage to enable MSTM
  await page.evaluate(() => {
    try {
      const state = JSON.parse(localStorage.getItem('awesome_chart_state_v1'));
      if (state && state.charts && state.charts[0]) {
        state.charts[0].showMSTM = true;
        localStorage.setItem('awesome_chart_state_v1', JSON.stringify(state));
      }
    } catch (e) {}
  });
  
  // Reload page to apply localStorage
  await page.reload({ waitUntil: 'networkidle0' });
  await new Promise(r => setTimeout(r, 3000));
  
  // Dump cached targets from the renderer somehow?
  // We can't access it directly. Let's just look at the logs.
  await page.screenshot({ path: 'screenshot.png' });
  console.log('Screenshot saved to screenshot.png');
  
  await browser.close();
})();
