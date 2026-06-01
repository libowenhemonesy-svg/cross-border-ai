/**
 * 插件弹窗脚本
 * 功能：处理用户交互，与content.js通信，显示商品信息
 */

// 全局变量存储提取的商品数据
let currentProductData = null;

// Amazon Agent 后端地址（本地开发）
const BACKEND_URL = 'http://localhost:8010';

// 页面加载完成后初始化
document.addEventListener('DOMContentLoaded', function() {
  // 获取DOM元素
  const extractBtn = document.getElementById('extractBtn');
  const messageSection = document.getElementById('messageSection');
  const messageText = document.getElementById('messageText');
  const productInfo = document.getElementById('productInfo');
  const showReviewsBtn = document.getElementById('showReviewsBtn');
  const closeReviewsBtn = document.getElementById('closeReviewsBtn');
  const sendToBackend = document.getElementById('sendToBackend');

  // 绑定按钮点击事件
  extractBtn.addEventListener('click', extractProductInfo);
  showReviewsBtn.addEventListener('click', toggleReviews);
  closeReviewsBtn.addEventListener('click', closeReviews);
  sendToBackend.addEventListener('click', sendDataToBackend);

  // 页面加载时检查当前标签页是否是Amazon页面
  checkCurrentTab();
});

/**
 * 切换评论显示状态
 */
async function toggleReviews() {
  const reviewsSection = document.getElementById('reviewsSection');
  const reviewsList = document.getElementById('reviewsList');

  if (reviewsSection.classList.contains('hidden')) {
    // 显示评论区域
    reviewsSection.classList.remove('hidden');
    reviewsList.innerHTML = '<p class="loading-text">正在加载评论...</p>';

    // 获取评论数据
    try {
      const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });

      // 先尝试注入 content script（如果未加载）
      try {
        await chrome.scripting.executeScript({
          target: { tabId: tab.id },
          files: ['content.js']
        });
      } catch (e) {
        // 忽略注入错误，可能已经加载
      }

      // 等待一小段时间
      await new Promise(resolve => setTimeout(resolve, 300));

      const response = await sendMessageToContentScript(tab.id, {
        action: 'GET_REVIEWS'
      });

      if (response && response.success) {
        displayReviews(response.data);
      } else {
        const errorMsg = response ? response.error : '无法获取评论';
        reviewsList.innerHTML = `<p class="loading-text">获取失败: ${errorMsg}</p>`;
      }
    } catch (error) {
      console.error('获取评论失败:', error);
      reviewsList.innerHTML = `<p class="loading-text">获取评论失败: ${error.message}</p>`;
    }
  } else {
    // 隐藏评论区域
    reviewsSection.classList.add('hidden');
  }
}

/**
 * 关闭评论区域
 */
function closeReviews() {
  const reviewsSection = document.getElementById('reviewsSection');
  reviewsSection.classList.add('hidden');
}

/**
 * 显示差评列表
 * @param {Array} reviews - 差评数据数组
 */
function displayReviews(reviews) {
  const reviewsList = document.getElementById('reviewsList');
  const reviewsHeader = document.querySelector('.reviews-header h4');

  if (reviewsHeader) {
    reviewsHeader.textContent = '差评分析';
  }

  if (!reviews || reviews.length === 0) {
    reviewsList.innerHTML = '<p class="loading-text">暂无差评数据</p>';
    return;
  }

  // 检查是否是提示信息
  if (reviews.length === 1 && reviews[0].title === '提示') {
    reviewsList.innerHTML = `<p class="loading-text">${escapeHtml(reviews[0].content)}</p>`;
    return;
  }

  let html = `<p class="reviews-summary">共找到 ${reviews.length} 条差评</p>`;

  reviews.forEach(review => {
    const stars = '★'.repeat(review.rating || 0) + '☆'.repeat(5 - (review.rating || 0));

    html += `
      <div class="review-item negative-review">
        <div class="review-header">
          <div class="review-rating">
            <span class="review-stars negative-stars">${stars}</span>
            <span class="rating-text">${review.rating || 0}星</span>
          </div>
          <span class="review-date">${review.date || ''}</span>
        </div>
        ${review.title ? `<p class="review-title">${escapeHtml(review.title)}</p>` : ''}
        <p class="review-content">${escapeHtml(review.content || '无评论内容')}</p>
      </div>
    `;
  });

  reviewsList.innerHTML = html;
}

/**
 * HTML转义函数
 * @param {string} text - 原始文本
 * @returns {string} - 转义后的文本
 */
function escapeHtml(text) {
  if (!text) return '';
  const div = document.createElement('div');
  div.textContent = text;
  return div.innerHTML;
}

/**
 * 发送数据到 Amazon Agent 后端
 */
async function sendDataToBackend() {
  if (!currentProductData) {
    showMessage('没有可发送的数据，请先提取商品信息');
    return;
  }

  const sendBtn = document.getElementById('sendToBackend');

  try {
    // 禁用按钮
    sendBtn.disabled = true;
    sendBtn.innerHTML = '<span class="loading"></span>发送中...';

    // 获取评论数据
    let reviews = [];
    const reviewsSection = document.getElementById('reviewsSection');
    if (!reviewsSection.classList.contains('hidden')) {
      // 如果评论区域已打开，获取评论数据
      try {
        const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
        const response = await sendMessageToContentScript(tab.id, {
          action: 'GET_REVIEWS'
        });
        if (response && response.success) {
          reviews = response.data;
        }
      } catch (e) {
        console.log('获取评论失败:', e);
      }
    }

    // 准备发送的数据
    const payload = {
      title: currentProductData.title || '',
      price: currentProductData.price || '',
      rating: currentProductData.rating || '',
      review_count: currentProductData.review_count || currentProductData.reviewCount || '',
      bullets: currentProductData.bullets || [],
      image: currentProductData.image || '',
      url: currentProductData.url || '',
      asin: currentProductData.asin || '',
      reviews: reviews || []
    };

    // 发送到后端
    const response = await fetch(`${BACKEND_URL}/api/chrome/submit`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(payload)
    });

    const result = await response.json();

    if (result.success) {
      showMessage(`数据已成功发送到 Amazon Agent！ASIN: ${result.asin || '未找到'}`);
    } else {
      showMessage(`发送失败: ${result.error || '未知错误'}`);
    }

  } catch (error) {
    console.error('发送数据失败:', error);
    showMessage(`发送失败: ${error.message}。请确保 Amazon Agent 后端已启动。`);
  } finally {
    // 恢复按钮状态
    sendBtn.disabled = false;
    sendBtn.innerHTML = `
      <svg class="btn-icon" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
        <path d="M22 2L11 13" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
        <path d="M22 2L15 22L11 13L2 9L22 2Z" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
      </svg>
      发送到 Amazon Agent 后端
    `;
  }
}

/**
 * 检查当前标签页是否是Amazon商品页面
 */
async function checkCurrentTab() {
  try {
    // 获取当前活动标签页
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });

    // 检查是否是Amazon页面
    if (!tab.url || !tab.url.includes('amazon.com')) {
      showMessage('请打开 Amazon 商品详情页后再使用此插件');
      document.getElementById('extractBtn').disabled = true;
    }
  } catch (error) {
    console.error('检查标签页失败:', error);
  }
}

/**
 * 提取商品信息的主函数
 */
async function extractProductInfo() {
  const extractBtn = document.getElementById('extractBtn');
  const productInfo = document.getElementById('productInfo');

  try {
    // 禁用按钮并显示加载状态
    extractBtn.disabled = true;
    extractBtn.innerHTML = '<span class="loading"></span>提取中...';

    // 隐藏之前的消息和信息
    hideMessage();
    productInfo.classList.add('hidden');

    // 获取当前活动标签页
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });

    // 检查是否是Amazon页面
    if (!tab.url || !tab.url.includes('amazon.com')) {
      showMessage('请打开 Amazon 商品详情页后再使用此插件');
      return;
    }

    // 等待页面完全加载
    if (tab.status !== 'complete') {
      showMessage('页面正在加载中，请稍后再试...');
      return;
    }

    // 向content.js发送消息
    const response = await sendMessageToContentScript(tab.id, {
      action: 'GET_PRODUCT_INFO'
    });

    // 处理响应
    if (response && response.success) {
      displayProductInfo(response.data);
    } else {
      const errorMsg = response ? response.error : '无法获取商品信息';
      showMessage(`提取失败: ${errorMsg}`);
    }

  } catch (error) {
    console.error('提取商品信息失败:', error);
    showMessage(`发生错误: ${error.message}`);
  } finally {
    // 恢复按钮状态
    extractBtn.disabled = false;
    extractBtn.innerHTML = `
      <svg class="btn-icon" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
        <path d="M21 15V19C21 19.5304 20.7893 20.0391 20.4142 20.4142C20.0391 20.7893 19.5304 21 19 21H5C4.46957 21 3.96086 20.7893 3.58579 20.4142C3.21071 20.0391 3 19.5304 3 19V15" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
        <polyline points="7 10 12 15 17 10" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
        <line x1="12" y1="15" x2="12" y2="3" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
      </svg>
      提取当前商品信息
    `;
  }
}

/**
 * 检查content script是否已加载
 * @param {number} tabId - 标签页ID
 * @returns {Promise<boolean>} - 是否已加载
 */
async function isContentScriptLoaded(tabId) {
  try {
    const [result] = await chrome.scripting.executeScript({
      target: { tabId: tabId },
      func: () => window.__amazonAnalyzerLoaded || false
    });
    return result?.result || false;
  } catch {
    return false;
  }
}

/**
 * 向content.js发送消息
 * @param {number} tabId - 标签页ID
 * @param {Object} message - 要发送的消息
 * @returns {Promise<Object>} - 响应结果
 */
async function sendMessageToContentScript(tabId, message) {
  // 先检查content script是否已加载
  let isLoaded = await isContentScriptLoaded(tabId);

  if (!isLoaded) {
    console.log('Content script 未加载，尝试注入...');
    try {
      // 注入 content.js
      await chrome.scripting.executeScript({
        target: { tabId: tabId },
        files: ['content.js']
      });

      // 等待脚本初始化
      await new Promise(resolve => setTimeout(resolve, 200));

      // 再次检查是否加载成功
      isLoaded = await isContentScriptLoaded(tabId);
      if (!isLoaded) {
        throw new Error('Content script 注入失败');
      }
    } catch (injectError) {
      throw new Error('无法注入内容脚本: ' + injectError.message);
    }
  }

  // 发送消息
  return new Promise((resolve, reject) => {
    chrome.tabs.sendMessage(tabId, message, (response) => {
      if (chrome.runtime.lastError) {
        reject(new Error(chrome.runtime.lastError.message));
      } else {
        resolve(response);
      }
    });
  });
}

/**
 * 显示商品信息
 * @param {Object} data - 商品信息数据
 */
async function displayProductInfo(data) {
  const productInfo = document.getElementById('productInfo');

  // 显示商品图片
  const imageElement = document.getElementById('productImage');
  if (data.image && data.image !== '未找到') {
    imageElement.src = data.image;
    imageElement.style.display = 'block';
  } else {
    imageElement.style.display = 'none';
  }

  // 更新各个字段
  document.getElementById('productPrice').textContent = data.price || '未找到';
  document.getElementById('productRating').textContent = data.rating || '未找到';
  document.getElementById('productReviewCount').textContent = data.reviewCount || '未找到';
  document.getElementById('productASIN').textContent = data.asin || '未找到';

  // 处理URL显示
  const urlElement = document.getElementById('productUrl');
  if (data.url && data.url !== '未找到') {
    urlElement.textContent = data.url;
    urlElement.title = data.url; // 鼠标悬停显示完整URL
  } else {
    urlElement.textContent = '未找到';
  }

  // 显示标题
  const titleElement = document.getElementById('productTitle');
  const titleTranslation = document.getElementById('productTitleTranslation');

  if (data.title && data.title !== '未找到') {
    // 检测是否是中文
    if (isChinese(data.title)) {
      // 原文是中文，直接显示
      titleElement.textContent = data.title;
      titleTranslation.textContent = '';
    } else {
      // 原文是英文，需要翻译
      titleElement.textContent = data.title;
      titleTranslation.textContent = '翻译中...';

      try {
        const translatedTitle = await translateText(data.title);
        if (translatedTitle && translatedTitle !== data.title) {
          titleElement.textContent = translatedTitle;
          titleTranslation.textContent = `原文: ${data.title}`;
        } else {
          titleTranslation.textContent = '';
        }
      } catch (error) {
        titleTranslation.textContent = '';
      }
    }
  } else {
    titleElement.textContent = '未找到';
    titleTranslation.textContent = '';
  }

  // 处理五点描述
  const bulletsList = document.getElementById('productBullets');
  bulletsList.innerHTML = ''; // 清空现有内容

  if (data.bullets && data.bullets.length > 0) {
    for (const bullet of data.bullets) {
      const li = document.createElement('li');

      // 检测是否是中文
      if (isChinese(bullet)) {
        // 原文是中文，直接显示
        const textDiv = document.createElement('div');
        textDiv.className = 'bullet-translated';
        textDiv.textContent = bullet;
        li.appendChild(textDiv);
      } else {
        // 原文是英文，需要翻译
        const translatedText = document.createElement('div');
        translatedText.className = 'bullet-translated';
        translatedText.textContent = '翻译中...';

        const originalText = document.createElement('div');
        originalText.className = 'bullet-original';
        originalText.textContent = bullet;

        li.appendChild(translatedText);
        li.appendChild(originalText);

        // 异步翻译
        translateText(bullet).then(translated => {
          if (translated && translated !== bullet) {
            translatedText.textContent = translated;
          } else {
            translatedText.textContent = bullet;
            originalText.textContent = '';
          }
        }).catch(() => {
          translatedText.textContent = bullet;
          originalText.textContent = '';
        });
      }

      bulletsList.appendChild(li);
    }
  } else {
    const li = document.createElement('li');
    li.className = 'empty-item';
    li.textContent = '未找到五点描述';
    bulletsList.appendChild(li);
  }

  // 显示商品信息区域
  productInfo.classList.remove('hidden');

  // 显示发送按钮
  const sendSection = document.getElementById('sendSection');
  sendSection.classList.remove('hidden');

  // 保存当前数据
  currentProductData = data;

  // 隐藏消息区域
  hideMessage();
}

/**
 * 检测文本是否是中文
 * @param {string} text - 要检测的文本
 * @returns {boolean} - 是否是中文
 */
function isChinese(text) {
  if (!text) return false;
  // 中文字符的Unicode范围
  const chineseRegex = /[一-鿿㐀-䶿豈-﫿]/;
  // 如果中文字符占比超过30%，认为是中文
  const chineseChars = text.match(chineseRegex) || [];
  return chineseChars.length / text.length > 0.3;
}

/**
 * 翻译文本（简化版，不调用外部API）
 * @param {string} text - 要翻译的文本
 * @returns {Promise<string>} - 翻译后的文本
 */
async function translateText(text) {
  if (!text || text === '未找到') return '';
  // 直接返回原文，不调用翻译API
  return text;
}

/**
 * 显示提示消息
 * @param {string} message - 消息内容
 */
function showMessage(message) {
  const messageSection = document.getElementById('messageSection');
  const messageText = document.getElementById('messageText');

  messageText.textContent = message;
  messageSection.classList.remove('hidden');
}

/**
 * 隐藏提示消息
 */
function hideMessage() {
  const messageSection = document.getElementById('messageSection');
  messageSection.classList.add('hidden');
}

/**
 * 工具函数：格式化数字
 * @param {string} text - 包含数字的文本
 * @returns {string} - 格式化后的文本
 */
function formatNumber(text) {
  if (!text) return '未找到';

  // 提取数字部分
  const numberMatch = text.match(/[\d,]+\.?\d*/);
  if (numberMatch) {
    return numberMatch[0];
  }

  return text;
}

/**
 * 工具函数：截断长文本
 * @param {string} text - 原始文本
 * @param {number} maxLength - 最大长度
 * @returns {string} - 截断后的文本
 */
function truncateText(text, maxLength = 100) {
  if (!text) return '未找到';
  if (text.length <= maxLength) return text;
  return text.substring(0, maxLength) + '...';
}