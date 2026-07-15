const TelegramBot = require('node-telegram-bot-api');
const admin = require('firebase-admin');

// 1. Инициализация Telegram-бота
const token = '8631684388:AAGZ87I7RTu0pXLPw9SLdkPyaSPGHXVwHzk';
const bot = new TelegramBot(token, { polling: true });

// === НАСТРОЙКИ КЛУБА ===
const CLUB_CHANNEL_ID = '@Auto_Partners_Group'; 

// 2. Инициализация Firebase
let serviceAccount;
try {
    serviceAccount = require("./firebase-adminsdk-key.json");
} catch (e) {
    serviceAccount = JSON.parse(process.env.FIREBASE_CONFIG_JSON);
}

admin.initializeApp({
  credential: admin.credential.cert(serviceAccount),
  databaseURL: "https://apg-site-56d91-default-rtdb.firebaseio.com/"
});

const db = admin.database();
console.log("🤖 Бот APG запущен. Полное администрирование чата и сайта активно...");

// Хранилище сессий авторизованных админов
const authorizedAdmins = new Set();

// Вход в админ-панель по коду apg1
bot.onText(/\/admin (.+)/, (msg, match) => {
    const chatId = msg.chat.id;
    const password = match[1].trim();

    if (password === 'apg1') {
        authorizedAdmins.add(chatId);
        sendAdminMenu(chatId);
    } else {
        bot.sendMessage(chatId, "❌ Неверный пароль администратора!");
    }
});

function sendAdminMenu(chatId) {
    const opts = {
        reply_markup: {
            keyboard: [
                ['📦 Управление услугами', '💬 Все отзывы'],
                ['🚗 Все карточки', '🏆 Достижения'],
                ['🚪 Выйти из панели']
            ],
            resize_keyboard: true,
            one_time_keyboard: false
        },
        parse_mode: 'Markdown'
    };
    bot.sendMessage(chatId, "👑 *Вы вошли в панель администратора APG!*\n\nВсе уведомления о новых карточках и отзывах теперь приходят и на сайт, и тебе сюда.", opts);
}

bot.onText(/🚪 Выйти из панели/, (msg) => {
    const chatId = msg.chat.id;
    if (authorizedAdmins.has(chatId)) {
        authorizedAdmins.delete(chatId);
        bot.sendMessage(chatId, "Вы вышли из панели администратора.", {
            reply_markup: { remove_keyboard: true }
        });
    }
});

function isAdmin(chatId) {
    return authorizedAdmins.has(chatId);
}

// ==========================================
// МОДЕРАЦИЯ И ОПОВЕЩЕНИЯ (ТОЛЬКО ДЛЯ АВТ. АДМИНОВ)
// ==========================================

db.ref('cards').on('child_added', (snapshot) => {
    const cardId = snapshot.key;
    const cardData = snapshot.val();

    if (cardData.status === 'pending') {
        authorizedAdmins.forEach(adminId => {
            const message = `🚗 *Новая карточка на модерацию!*\n\n👤 *Никнейм:* ${cardData.author}\n🚘 *Автомобиль:* ${cardData.car || 'Не указан'}\n🔥 *Роль:* ${cardData.role || 'Участник'}`;
            
            const opts = {
                chat_id: adminId,
                parse_mode: 'Markdown',
                reply_markup: {
                    inline_keyboard: [
                        [
                            { text: 'Одобрить ✅', callback_data: `approve_card:${cardId}` },
                            { text: 'Отклонить ❌', callback_data: `reject_card:${cardId}` }
                        ]
                    ]
                }
            };
            
            bot.sendPhoto(adminId, cardData.url, { caption: message, parse_mode: 'Markdown', reply_markup: opts.reply_markup })
               .catch(err => console.error(err));
        });
    }
});

db.ref('reviews').on('child_added', (snapshot) => {
    const reviewId = snapshot.key;
    const reviewData = snapshot.val();

    if (reviewData.status === 'pending') {
        authorizedAdmins.forEach(adminId => {
            const stars = '★'.repeat(reviewData.stars) + '☆'.repeat(5 - reviewData.stars);
            const message = `💬 *Новый отзыв на модерацию!*\n\n👤 *Автор:* ${reviewData.author}\n⭐️ *Оценка:* ${stars}\n📝 *Текст:* ${reviewData.text}`;
            
            const opts = {
                reply_markup: {
                    inline_keyboard: [
                        [
                            { text: 'Одобрить ✅', callback_data: `approve_review:${reviewId}` },
                            { text: 'Отклонить ❌', callback_data: `reject_review:${reviewId}` }
                        ]
                    ]
                },
                parse_mode: 'Markdown'
            };
            
            bot.sendMessage(adminId, message, opts);
        });
    }
});

// Уведомления о наградах
db.ref('achievements').on('child_added', (snapshot) => {
    const achievement = snapshot.val();
    if (achievement.notified !== true) {
        bot.sendPhoto(CLUB_CHANNEL_ID, achievement.url, {
            caption: `🏆 *Наши достижения пополнились!*\n\n👉 ${achievement.title || 'Новая награда нашего клуба APG!'}`,
            parse_mode: 'Markdown'
        }).then(() => {
            db.ref(`achievements/${snapshot.key}`).update({ notified: true });
        }).catch(err => console.error(err));
    }
});

// ==========================================
// КОМАНДЫ АДМИНА В ЧАТЕ БОТА
// ==========================================
bot.on('message', async (msg) => {
    const chatId = msg.chat.id;
    const text = msg.text;

    if (!isAdmin(chatId)) return;

    if (text === '📦 Управление услугами') {
        const snap = await db.ref('services').once('value');
        const services = snap.val();

        if (!services) {
            return bot.sendMessage(chatId, "Список услуг пуст. Для добавления отправь:\n`/add_service Название | Описание | Цена | @tg`", { parse_mode: 'Markdown' });
        }

        let msgText = "🔧 *Текущие услуги на сайте:*\n\n";
        const keyboard = [];

        Object.keys(services).forEach(key => {
            const s = services[key];
            msgText += `• *${s.title}* (${s.price || 'Цена не указана'})\n`;
            keyboard.push([{ text: `❌ Удалить: ${s.title.substring(0, 20)}...`, callback_data: `del_service:${key}` }]);
        });

        bot.sendMessage(chatId, msgText, {
            parse_mode: 'Markdown',
            reply_markup: { inline_keyboard: keyboard }
        });
    }

    if (text === '💬 Все отзывы') {
        const snap = await db.ref('reviews').once('value');
        const reviews = snap.val();

        if (!reviews) return bot.sendMessage(chatId, "На сайте пока нет отзывов.");

        const keyboard = [];
        let msgText = "💬 *Опубликованные отзывы на сайте:*\n\n";

        Object.keys(reviews).forEach(key => {
            const r = reviews[key];
            if (r.status === 'approved') {
                msgText += `• *${r.author}*: "${r.text.substring(0, 30)}..."\n`;
                keyboard.push([{ text: `🗑 Удалить отзыв от ${r.author}`, callback_data: `del_review:${key}` }]);
            }
        });

        bot.sendMessage(chatId, msgText, {
            parse_mode: 'Markdown',
            reply_markup: { inline_keyboard: keyboard }
        });
    }

    if (text === '🚗 Все карточки') {
        const snap = await db.ref('cards').once('value');
        const cards = snap.val();

        if (!cards) return bot.sendMessage(chatId, "На сайте пока нет карточек участников.");

        const keyboard = [];
        let msgText = "🚗 *Одобренные карточки участников:*\n\n";

        Object.keys(cards).forEach(key => {
            const c = cards[key];
            if (c.status === 'approved') {
                msgText += `• *${c.author}* — ${c.car}\n`;
                keyboard.push([{ text: `🗑 Удалить карточку: ${c.author}`, callback_data: `del_card:${key}` }]);
            }
        });

        bot.sendMessage(chatId, msgText, {
            parse_mode: 'Markdown',
            reply_markup: { inline_keyboard: keyboard }
        });
    }

    if (text === '🏆 Достижения') {
        bot.sendMessage(chatId, "Чтобы загрузить новую награду на сайт, отправь мне фотку награды и добавь к ней подпись, которая начинается с текста `Награда: [Название]`");
    }
});

// Добавление услуги
bot.onText(/\/add_service (.+)/, async (msg, match) => {
    const chatId = msg.chat.id;
    if (!isAdmin(chatId)) return;

    const parts = match[1].split('|').map(p => p.trim());
    if (parts.length < 2) {
        return bot.sendMessage(chatId, "⚠️ Неверный формат! Пример:\n`/add_service Сход-Развал | Быстро и ровно | 1500 руб | @lenar_apg`", { parse_mode: 'Markdown' });
    }

    const [title, desc, price, tg] = parts;
    await db.ref('services').push({ title, desc: desc || '', price: price || '', tg: tg || '' });
    bot.sendMessage(chatId, "✅ Новая услуга добавлена на сайт!");
});

// Загрузка фото наград
bot.on('photo', async (msg) => {
    const chatId = msg.chat.id;
    if (!isAdmin(chatId)) return;

    const caption = msg.caption || '';
    if (caption.startsWith('Награда:')) {
        const title = caption.replace('Награда:', '').trim();
        const photoId = msg.photo[msg.photo.length - 1].file_id;
        const fileLink = await bot.getFileLink(photoId);

        await db.ref('achievements').push({ title: title || 'Награда APG', url: fileLink, notified: false });
        bot.sendMessage(chatId, "🏆 Награда успешно добавлена на сайт и отправлена в канал!");
    }
});

// Callback-кнопки
bot.on('callback_query', async (query) => {
    const data = query.data;
    const [action, id] = data.split(':');
    const chatId = query.message.chat.id;

    try {
        if (action === 'approve_card') {
            await db.ref(`cards/${id}`).update({ status: 'approved' });
            bot.answerCallbackQuery(query.id, { text: 'Карточка одобрена!' });
            bot.deleteMessage(chatId, query.message.message_id);
            
            const snap = await db.ref(`cards/${id}`).once('value');
            const card = snap.val();
            bot.sendPhoto(CLUB_CHANNEL_ID, card.url, {
                caption: `⚡ *Встречайте нового участника APG Family!*\n\n👤 *Никнейм:* ${card.author}\n🚗 *Автомобиль:* ${card.car}\n🔥 *Роль:* ${card.role}\n\nСделай свою карточку на сайте и попади в канал!`,
                parse_mode: 'Markdown'
            });

        } else if (action === 'reject_card') {
            await db.ref(`cards/${id}`).remove();
            bot.answerCallbackQuery(query.id, { text: 'Карточка удалена.' });
            bot.deleteMessage(chatId, query.message.message_id);

        } else if (action === 'approve_review') {
            await db.ref(`reviews/${id}`).update({ status: 'approved' });
            bot.answerCallbackQuery(query.id, { text: 'Отзыв одобрен!' });
            bot.deleteMessage(chatId, query.message.message_id);
            
            const snap = await db.ref(`reviews/${id}`).once('value');
            const rev = snap.val();
            const stars = '⭐️'.repeat(rev.stars);
            bot.sendMessage(CLUB_CHANNEL_ID, `🔥 *Новый отзыв с нашего сайта!*\n\n👤 *Автор:* ${rev.author}\nОценка: ${stars}\n\n💬 "${rev.text}"`);

        } else if (action === 'reject_review') {
            await db.ref(`reviews/${id}`).remove();
            bot.answerCallbackQuery(query.id, { text: 'Отзыв удален.' });
            bot.deleteMessage(chatId, query.message.message_id);

        } else if (action === 'del_service') {
            await db.ref(`services/${id}`).remove();
            bot.answerCallbackQuery(query.id, { text: 'Услуга удалена с сайта!' });
            bot.deleteMessage(chatId, query.message.message_id);

        } else if (action === 'del_review') {
            await db.ref(`reviews/${id}`).remove();
            bot.answerCallbackQuery(query.id, { text: 'Отзыв удален с сайта!' });
            bot.deleteMessage(chatId, query.message.message_id);

        } else if (action === 'del_card') {
            await db.ref(`cards/${id}`).remove();
            bot.answerCallbackQuery(query.id, { text: 'Карточка удалена с сайта!' });
            bot.deleteMessage(chatId, query.message.message_id);
        }
    } catch (e) {
        console.error("Ошибка при работе инлайн кнопок:", e);
    }
});

// Авторизация
bot.onText(/\/start (.+)/, async (msg, match) => {
    const chatId = msg.chat.id;
    const startParam = match[1];

    if (startParam.startsWith('auth_')) {
        const tempToken = startParam.split('auth_')[1];
        await db.ref(`auth_sessions/${tempToken}`).set({
            telegram_id: chatId,
            username: msg.from.username ? `@${msg.from.username}` : msg.from.first_name,
            status: 'completed'
        });
        bot.sendMessage(chatId, `🎉 *Авторизация успешна!*\n\nВернитесь на сайт, вы вошли в профиль.`);
    }
});