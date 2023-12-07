import telebot
import time
from telebot import types
import requests
import atexit
import pickle
import openai
import asyncio
from threading import Thread
import traceback
import sys


def run(func):
    func()
    return func

help_string = ""
commands = dict()

threaded_runs = []

def run_threaded(func):
    def async_call(*argc,**argv):
        threaded_runs.append((func,argc,argv))
    return async_call

def catch_errors_on_command(func):
    def err_catcher(message,*argc,**argv):
        try:
            func(message,*argc,**argv)
        except BaseException as e:
            traceback.print_exception(*sys.exc_info())
            bot.send_message(message.from_user.id, text=f'Ошибка: {e}')
    return err_catcher


def register_command(name,description):
    global help_string
    help_string=f"{help_string}\n/{name} - {description}"
    def register(func):
        commands[name]=func
        return func
    
    return register


# Создаем экземпляр бота
bot = telebot.TeleBot(open("token.txt","r").read())

def write_user_data():
    with open("users.pickle","wb") as f:
        pickle.dump(users,f)

    

try:
    with open("users.pickle","rb") as f:
        users = pickle.load(f)
except Exception as e:
    print(e)
    users = dict()
    
if users is None:
    users = dict()

def get_user_data(message):
    return users[message.from_user.username]

@register_command("mode","set used mode")
@run_threaded
@catch_errors_on_command
def mode(message):
    keyboard = types.InlineKeyboardMarkup()
    key_continue = types.InlineKeyboardButton(text='Продолжение', callback_data='mode.continue')
    key_chat = types.InlineKeyboardButton(text='Чат', callback_data='mode.chat')
    key_1resp = types.InlineKeyboardButton(text='1 вопрос 1 ответ', callback_data='mode.new_msg')
    key_simple_continue = types.InlineKeyboardButton(text='continue_simple', callback_data='mode.continue_simple')
    keyboard.add(key_continue)
    keyboard.add(key_chat)
    keyboard.add(key_1resp)
    keyboard.add(key_simple_continue)
    bot.send_message(message.from_user.id, text='Выберите режим', reply_markup=keyboard)
    
@register_command("model","choose modes")
@run_threaded
@catch_errors_on_command
def model(message):
    url = settings['url']+'internal/model/list'
    response = requests.get(url, verify=False)
    try:
        models = response.json()['model_names']
        keyboard = types.InlineKeyboardMarkup()
        for model in models:
            key = types.InlineKeyboardButton(text=f'{model}', callback_data=f'model.{model}')
            keyboard.add(key)
        bot.send_message(message.from_user.id, text='Выберите модель:', reply_markup=keyboard)
    except Exception as e:
        bot.send_message(message.from_user.id, text=f'Неизвестная ошибка: {e}, ответ api был: {response}')
    
    pass

@register_command("unload","unload model")
@run_threaded
@catch_errors_on_command
def unload(message):
    url = settings['url']+'internal/model/unload'
    response = requests.post(url, verify=False)
    if(not response.status_code==200):
        bot.send_message(message.from_user.id, text=f'Провал: {response}')
    else:
        bot.send_message(message.from_user.id, text=f'ОК')
        
        
@register_command("response_size","sets size of response")
@run_threaded
@catch_errors_on_command
def set_size(message):
    keyboard = types.InlineKeyboardMarkup()
    for size in [50,100,200,400,500,800,1024,1600,2048,4096]:
        key = types.InlineKeyboardButton(text=f'{size}', callback_data=f'size.{size}')
        keyboard.add(key)
    bot.send_message(message.from_user.id, text='Выберите размер:', reply_markup=keyboard)
    
@register_command("profile","get user profile")
@run_threaded
@catch_errors_on_command
def profile(message):
    user_data = get_user_data(message)
    response = f'''
    {user_data}
'''
    bot.send_message(message.from_user.id, text=response)
    
@register_command("reset","reset context")
@run_threaded
@catch_errors_on_command
def profile(message):
    user_data = get_user_data(message)
    user_data['history']=[]
    bot.send_message(message.from_user.id, text='контекст сброшен')

@register_command("help","show this mesage")
@run_threaded
@catch_errors_on_command
def help(message):
    bot.send_message(message.chat.id, help_string)
    
        
def process_command(message):
    if(message.text[0]!='/'):
        return False
    cmd = message.text[1:max(len(message.text),message.text.find(' '))]
    if cmd in commands:
        callback = commands[cmd]
        callback(message)
        return True
            
    return False
        
@run_threaded
@catch_errors_on_command
def generate(message):
    url = settings['url']+'chat/completions'
    headers = {
        "Content-Type": "application/json"
    }

    user_data = get_user_data(message)
    history:any
    if('history' in user_data):
        history=user_data['history']
    else:
        history=[]
        user_data['history']=history
        
    if(user_data['mode'] in ['new_msg','continue_simple'] ):
        history=[]
        
        
    if(user_data['mode'] in ['continue','continue_simple']):
        history.append({"content": message.text})
    else:
        history.append({"role": "user", "content": message.text})
    
    

    
    data = {
        "max_tokens":200 if not 'response_size' in user_data else user_data['response_size'],
        #"mode": "chat" if user_data['mode'] in ['chat','new_msg'] else 'continue',
        "mode": "chat",
        "character": "Assistant",
        "messages": history
    }
    
    @run_threaded
    def msg_generating(mesage):
        bot.send_message(message.from_user.id, text=f'generating')  
        
    msg_generating(message)

    response = requests.post(url, headers=headers, json=data, verify=False)
    assistant_message = response.json()['choices'][0]['message']['content']
    history.append({"role": "assistant", "content": assistant_message})
    print(assistant_message)
    if(len(assistant_message)<4000):
        bot.send_message(message.from_user.id, text=f'{assistant_message}')    
    else:
        msg = ""
        for part in assistant_message.split('\n'):
            if(len(msg)+len(part)>4000):
                bot.send_message(message.from_user.id, text=f'{msg}') 
                msg = part
            else:
                msg+='\n'
                msg+=part
        if(len(msg)>3):
            bot.send_message(message.from_user.id, text=f'{msg}') 
    
@run
def load_settings():
    global settings 
    global elevated_users
    settings = eval(open("settings.py","r").read())
    elevated_users = settings["elevated_users"]
    openai.api_key = None if not 'key' in settings else settings["key"]
    openai.base_url = None if not 'url' in settings else settings["url"]
# Функция, обрабатывающая команду /start
@bot.message_handler(commands=["start"])
def start(m, res=False):
    print(m)
    # записать пользователя прям сразу тут в users

    bot.send_message(m.chat.id, 'Я на связи. Напиши мне что-нибудь )')
# Получение сообщений от юзера
@bot.message_handler(content_types=["text"])
def handle_text(message):
    user = message.from_user.username
    if(message.from_user.username not in elevated_users):
        print(f"incorrect username: {message.from_user.username}")
        return
    user_data:any
    if not user in users:
        user_data = dict()
        users[user]=user_data
    else:
        user_data = users[user]
    
    if(message.text.startswith('/')):
        if(not process_command(message)):
            bot.send_message(message.from_user.id, f'Неизвестная команда: {message.text}')
        return
    
        
    if(not 'mode' in user_data):
        user_data['mode']='chat'
    
    generate(message)
    

@bot.callback_query_handler(func=lambda call: True)
def callback_worker(call):
    user_data = get_user_data(call)
    data:str = call.data
    mode = data.split('.')
    category = mode[0]
    match category:
        case 'mode':
            type = mode[1]
            if(not 'mode' in user_data):
                user_data['mode']='none'
            if(user_data['mode']!=type):
                user_data['mode']=type
                user_data['history']=[]
                bot.send_message(call.from_user.id,"новый режим: %s"%type)
        case 'model':
            model = data[data.find('.')+1:]
            url = settings['url']+'internal/model/load'
            data = {
            "model_name":model
            }
            
            headers = {
                "Content-Type": "application/json"
            }
            response = requests.post(url, json=data,headers=headers,verify=False)
            if(response.status_code==200):
                bot.send_message(call.from_user.id,"новая модель: %s"%model)
            else:
                bot.send_message(call.from_user.id,f"Ошибка при попытке загрузить модель {response}")
        case 'size':
            user_data['response_size']=int(mode[1])
            bot.send_message(call.from_user.id,f"Новый размер ответа: {mode[1]}")
            

@atexit.register
def exit_handler():
    write_user_data()

@run
@run_threaded
def run_bot():         
    lasterr = 0
    # Запускаем бота
    while True:
        if(time.time()-lasterr>8):
            lasterr=time.time()
            try:
                print('restarting')
                bot.infinity_polling(timeout=10, long_polling_timeout = 5)
            except Exception as e:
                print(e)
                if(isinstance(e,KeyboardInterrupt)):
                    break
        else:
            break

@run
def run_anything():
    while(True):
        global threaded_runs
        time.sleep(0.1)
        for func,argc,argv in threaded_runs:
            def call():
                func(*argc,**argv)
            
            t = Thread(target=call)
            t.start()
        threaded_runs = []
            