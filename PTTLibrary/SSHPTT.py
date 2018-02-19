﻿import sys
import time
import re
import threading
import progressbar
import socket
import paramiko

try:
    from . import Util
    from . import Version
    from . import ErrorCode
    from . import Information
except SystemError:
    import Util
    import Version
    import ErrorCode
    import Information

Debug = True

Version = Version.Ver
LogLevel = Information.LogLevel()
PushType = Information.PushType()
ErrorCode = ErrorCode.ErrorCode()

class Library(object):
    def __init__(self, ID, Password, kickOtherLogin=True, _LogLevel=-1):

        self.__host = 'ptt.cc'
        self.__ID = ID
        self.__Password = Password
        self.__kickOtherLogin = kickOtherLogin

        self.ReplyPost_Board =                  1
        self.ReplyPost_Mail =                   2

        self.__LoginMode_Login =                1
        self.__LoginMode_Recover =              2
        self.__LoginMode_MultiLogin =           3

        self.__Refresh =                    '\x0C'

        # screen size
        self.width = 80
        self.height = 24
        # screen buffer
        self.screen = ''
        self.buf_size = self.width * self.height

        self.__LogLevel = LogLevel.INFO

        if _LogLevel != -1:
            if _LogLevel < LogLevel.DEBUG or LogLevel.SLIENT < _LogLevel:
                self.Log('LogLevel error: ' + str(_LogLevel))
                return None
            else:
                self.__LogLevel = _LogLevel

        self.__DefaultTimeout =                 5
        
        self.__Cursor =                       '>'
        
        self.__MaxMultiLogin =                  3

        self.__ConnectList = [None] * self.__MaxMultiLogin
        self.__ReceiveData = [''] * self.__MaxMultiLogin
        self.__PreReceiveData = [''] * self.__MaxMultiLogin
        self.__isConnected = [False] * self.__MaxMultiLogin

        self.QQ = 0
        ###############################

        self.__KickTimes =                      0
        
        self.__ShowProgressBar =             True
        
        self.__TimeoutCountMax =                3
        
        self.__RequestCount =                   0
        self.__MaxRequestCount =                1
        self.__MinRequestCount =                1
                
        self.__Timeout = [10] * self.__MaxMultiLogin
        self.__SleepTime = [0.5] * self.__MaxMultiLogin
        self.__TimeoutCount = [0] * self.__MaxMultiLogin
        
        self.__CrawPool = []
        
        self.__isBackground = False

        try:
            self.Log('偵測到前景執行使用編碼: ' + sys.stdin.encoding)
            self.__isBackground = False
        except Exception:
            self.Log('偵測到背景執行')
            self.__isBackground = True
        self.Log('使用者帳號: ' + ID)
        TempPW = ''

        for i in range(len(Password)):
            TempPW += '*'
        
        self.Log('密碼: ' + TempPW)
        if kickOtherLogin:
            self.Log('此連線將"會"剔除其他登入')
        else :
            self.Log('此連線將"不會"剔除其他登入')
        
        self.__connectRemote(0)
    
    def __showScreen(self, ErrCode, CatchIndex, ConnectIndex=0):
        if self.__LogLevel == LogLevel.DEBUG or Debug:
            print('-' * 50)
            print(self.__PreReceiveData[ConnectIndex])
            print('-' * 50)
            print(self.__ReceiveData[ConnectIndex])
            print('-' * 50)
            print('ErrorCode: ' + str(ErrCode))
            print('CatchIndex: ' + str(CatchIndex))
                                    
    def setLogLevel(self, _LogLevel):
        if _LogLevel < LogLevel.DEBUG or LogLevel.SLIENT < _LogLevel:
            self.Log('LogLevel error')
            return ErrorCode.ErrorInput
        self.__LogLevel = _LogLevel
        return ErrorCode.Success
    def Log(self, Message, _LogLevel=-1):
        if _LogLevel == -1:
            _LogLevel = LogLevel.INFO
        if _LogLevel < LogLevel.DEBUG or LogLevel.CRITICAL < _LogLevel:
            self.Log('LogLevel error')
            return ErrorCode.ErrorInput
        
        if self.__LogLevel <= _LogLevel:
            if _LogLevel == LogLevel.DEBUG:
                Prefix = '[除錯] '
            elif _LogLevel == LogLevel.WARNING:
                Prefix = '[警告] '
            elif _LogLevel == LogLevel.INFO:
                Prefix = '[資訊] '
            elif _LogLevel == LogLevel.CRITICAL:
                Prefix = '[重要] '
        
            Util.Log(Prefix + Message)
        return ErrorCode.Success
    def isLoginSuccess(self, ConnectIndex=0):
        return self.__isConnected[ConnectIndex]
    def __operatePTT(self, ConnectIndex, SendMessage='', CatchTargetList=[], Refresh=False, ExtraWait=0):
        
        SendMessageTimeout = 10.0

        if CatchTargetList == None:
            CatchTargetList = []
        
        ErrCode = ErrorCode.Success
        
        self.__PreReceiveData[ConnectIndex] = self.__ReceiveData[ConnectIndex]
        self.__ReceiveData[ConnectIndex] = ''

        try:
            if SendMessage != '':

                if Refresh:
                    SendMessage += self.__Refresh
                
                TimeCout = 0
                StartTime = time.time()
                time.sleep(0.02)
                while not self.__ConnectList[ConnectIndex].channel.send_ready():
                    time.sleep(0.01)

                    if TimeCout >= 100:
                        TimeCout = 0
                        NowTime = time.time()
                        if (NowTime - StartTime) >= SendMessageTimeout:
                            return ErrorCode.WaitTimeout, -1
                    TimeCout += 1

                self.__ConnectList[ConnectIndex].channel.send(SendMessage)
            
            if ExtraWait != 0:
                time.sleep(ExtraWait)
            
            TimeCout = 0
            StartTime = time.time()
            time.sleep(0.02)
            while not self.__ConnectList[ConnectIndex].channel.recv_ready():
                time.sleep(0.01)

                if TimeCout >= 100:
                    TimeCout = 0
                    NowTime = time.time()
                    if (NowTime - StartTime) >= SendMessageTimeout:
                        return ErrorCode.WaitTimeout, -1
                TimeCout += 1

            self.__ReceiveData[ConnectIndex] = self.__wait_str(ConnectIndex)

            while self.__ConnectList[ConnectIndex].channel.recv_ready():
                self.__ReceiveData[ConnectIndex] += self.__recv_str(ConnectIndex)
            
        except socket.timeout:
            ErrCode = ErrorCode.WaitTimeout

        self.__ReceiveData[ConnectIndex] = self.__cleanScreen(self.__ReceiveData[ConnectIndex])

        for i in range(len(CatchTargetList)):
            if CatchTargetList[i] in self.__ReceiveData[ConnectIndex]:
                self.__ConnectList[ConnectIndex].channel.settimeout(self.__DefaultTimeout)
                return ErrorCode.Success, i

        self.__ConnectList[ConnectIndex].channel.settimeout(self.__DefaultTimeout)

        return ErrCode, -1
    def __cleanScreen(self, screen):
        if not screen:
            return screen
            # remove color codes
        screen = re.sub('\[[\d+;]*[mH]', '', screen)
        # remove carriage return
        screen = re.sub(r'[\r]', '', screen)
        # remove escape cahracters, capabale of partial replace
        screen = re.sub(r'[\x00-\x08]', '', screen)
        screen = re.sub(r'[\x0b\x0c]', '', screen)
        screen = re.sub(r'[\x0e-\x1f]', '', screen)
        screen = re.sub(r'[\x7f-\xff]', '', screen)
        return screen
    def __wait_str(self, ConnectIndex):
        ch = ''
        while True:
            ch = self.__ConnectList[ConnectIndex].channel.recv(1)
            if ch:
                break
        return self.__dec_bytes(ch)
    def __recv_str(self, ConnectIndex):
        return self.__dec_bytes(self.__ConnectList[ConnectIndex].channel.recv(self.buf_size))
    # decode byte array to UTF-8 string
    def __dec_bytes(self, bytes):
        return bytes.decode('utf-8', errors = 'ignore')
    def __connectRemote(self, ConnectIndex):
        
        global ErrorCode

        self.__isConnected[ConnectIndex] = False

        RetryCount = 0
        Retry = False
        ErrCode = ErrorCode.Success

        while not self.__isConnected[ConnectIndex]:

            if Retry:
                Retry = False
                RetryCount += 1
                if RetryCount == 3:
                    return ErrCode
            else:
                RetryCount = 0
            
            try:
                self.__isConnected[ConnectIndex] = False
                if self.__ConnectList[ConnectIndex] != None:
                    self.__ConnectList[ConnectIndex] = None
                    self.Log('連線頻道 ' + str(ConnectIndex) + ' 重啟')
                else:
                    self.Log('連線頻道 ' + str(ConnectIndex) + ' 啟動')
                    # self.__ConnectList[ConnectIndex] = lib.(self.__host, self.__PortList[ConnectIndex])

                self.__ConnectList[ConnectIndex] = paramiko.SSHClient()
                self.__ConnectList[ConnectIndex].load_system_host_keys()
                self.__ConnectList[ConnectIndex].set_missing_host_key_policy(paramiko.WarningPolicy())
                self.__ConnectList[ConnectIndex].connect('ptt.cc', username = 'bbsu', password = '')
                
                self.__ConnectList[ConnectIndex].channel = self.__ConnectList[ConnectIndex].invoke_shell(width = self.width, height = self.height)
            except paramiko.AuthenticationException:
                # print('... Authentication failed')
                self.Log('連接至 ' + self.__host + ' SSH 認證失敗')
                return ErrorCode.SSHFail
            except Exception as e:
                # print('... Connection failed:', str(e))
                self.Log('連接至 ' + self.__host + ' 連線失敗')
                Retry = True
                ErrCode = ErrorCode.UnknowError
                continue
            except paramiko.SSHException:
                self.Log('建立互動通道失敗')
                Retry = True
                ErrCode = ErrorCode.UnknowError
                continue

            self.Log('建立互動通道成功')
            
            self.__ConnectList[ConnectIndex].channel.settimeout(self.__DefaultTimeout)

            SendMessage = ''
            Refresh = True
            ExtraWait = 0
            CatchList = [
                # 0
                '請輸入代號，或以 guest 參觀，或以 new 註冊:', 
                # 1
                '請輸入您的密碼:', 
                # 2
                '開始登入系統...',
                # 3
                '任意鍵',
                # 4
                '您想刪除其他重複登入的連線嗎？[Y/n]',
                # 5
                '【 編特別名單 】',
                # 6
                '您要刪除以上錯誤嘗試的記錄嗎?',
                # 7
                '為避免系統負荷過重, 請稍後再試',
                # 8
                '正在更新與同步線上使用者及好友名單，系統負荷量大時會需時較久...',
                #9
                '您有一篇文章尚未完成',
                #10
                '郵件選單',
                #11
                '請檢查帳號及密碼大小寫有無輸入錯誤',
            ]
            
            while True:
                ErrCode, CatchIndex = self.__operatePTT(ConnectIndex, SendMessage=SendMessage, CatchTargetList=CatchList, Refresh=Refresh, ExtraWait=ExtraWait)
                if ErrCode != ErrorCode.Success:
                    self.Log('登入操作失敗 錯誤碼: ' + str(ErrCode), LogLevel.DEBUG)
                    return ErrCode
                
                SendMessage = ''
                Refresh = False
                ExtraWait = 0

                if ErrCode != 0:
                    self.Log('登入失敗 錯誤碼: ' + str(ErrCode))
                    return ErrCode
                if CatchIndex == 0:
                    self.Log('連線至首頁')
                    self.Log('輸入帳號')
                    SendMessage = self.__ID + '\r'
                elif CatchIndex == 1:
                    self.Log('輸入密碼')
                    SendMessage = self.__Password + '\r'
                    Refresh = True
                elif CatchIndex == 2:
                    self.Log('登入成功!')
                    self.Log('等待載入主選單')
                    SendMessage = ' '
                    Refresh = True
                elif CatchIndex == 3:
                    self.Log('請按任意鍵繼續')
                    SendMessage = ' '
                    Refresh = True
                elif CatchIndex == 4:
                    if self.__kickOtherLogin:
                        self.Log('踢除其他登入...')
                        SendMessage = 'y\r'
                    else:
                        self.Log('不踢除其他登入...')
                        SendMessage = 'n\r'
                elif CatchIndex == 5:
                    self.Log('進入主選單')
                    self.__isConnected[ConnectIndex] = True
                    break
                elif CatchIndex == 6:
                    self.Log('刪除錯誤嘗試的記錄')
                    SendMessage = 'y\r'
                elif CatchIndex == 7:
                    self.Log('登入太頻繁 重新連線')
                    time.sleep(1)
                    Retry = True
                    ErrCode = ErrorCode.LoginFrequently
                    continue
                elif CatchIndex == 8:
                    self.Log('正在更新與同步線上使用者及好友名單')
                    time.sleep(2)
                    SendMessage = ' '
                    Refresh = True
                elif CatchIndex == 9:
                    self.Log('放棄尚未完成文章')
                    SendMessage = 'q\r'
                    ExtraWait = 1
                elif CatchIndex == 10:
                    self.Log('信件數目超出上限請整理')
                    return ErrorCode.MailBoxFull
                elif CatchIndex == 11:
                    self.Log('密碼錯誤')
                    return ErrorCode.WrongPassword
                else:
                    self.__showScreen(ErrCode, CatchIndex, ConnectIndex=ConnectIndex)
                    ErrCode = ErrorCode.UnknowError
                    Retry = True
                    # 若是沒有抓到適合的字串，表示可能誤進其他地方了，使用q 退出
                    SendMessage = 'qqqq'
                    continue

        if '> (' in self.__ReceiveData[ConnectIndex]:
            self.Log('新式游標模式')
            self.__Cursor = '>'
        elif '●(' in self.__ReceiveData[ConnectIndex]:
            self.Log('舊式游標模式')
            self.__Cursor = '●'
        else:
            self.Log('無法偵測游標')
            return ErrorCode.UnknowError
        return ErrorCode.Success
    def __gotoMainMenu(self, ConnectIndex=0):
        
        ErrCode, CatchIndex = self.__operatePTT(ConnectIndex, 'q\x1b[D\x1b[D\x1b[D\x1b[D', ['[呼叫器]', '編特別名單', '娛樂與休閒', '系統資訊區', '主功能表', '私人信件區'], Refresh=True)
        if ErrCode != ErrorCode.Success:
            return ErrCode
        if CatchIndex != -1:
            return ErrorCode.Success
        return ErrorCode.UnknowError
    def logout(self, ConnectIndex=-1):
        
        if ConnectIndex == -1:
            
            self.Log('準備登出所有頻道')
            
            for index in range(self.__MaxMultiLogin):
                self.__isConnected[index] = False
            
            for index in range(self.__MaxMultiLogin):
                if self.__ConnectList[index] == None:
                    # self.Log('連線 ' + str(index) + ' 未連接')
                    continue
                self.Log('頻道 ' + str(index) + ' 登出', LogLevel.DEBUG)
                ErrCode = self.__gotoMainMenu(index)
                if ErrCode != ErrorCode.Success:
                    self.Log('頻道 ' + str(index) + '登出出錯: ' + str(ErrCode))
                    continue
                
                SendMessage = 'g\ry\r'
                Refresh = False
                ExtraWait = 1

                ErrCode, CatchIndex = self.__operatePTT(index, SendMessage=SendMessage, CatchTargetList=['按任意鍵繼續'], Refresh=Refresh, ExtraWait=ExtraWait)
                if ErrCode != 0:
                    self.Log('頻道 ' + str(index) + '登出失敗 錯誤碼: ' + str(ErrCode))
                    return ErrorCode.UnknowError
                if CatchIndex == 0:
                    self.__ConnectList[index].channel.close()
                    self.__ConnectList[index].close()
                    self.__ConnectList[index] = None
                    self.Log('頻道 ' + str(index) + ' 登出成功')
                else:
                    self.__showScreen(ErrCode, CatchIndex, ConnectIndex)
                
        return ErrorCode.Success
    def getNewestPostIndex(self, Board):

        for i in range(3):
            ErrCode, NewestIndex = self.__getNewestPostIndex(Board, ConnectIndex = 0)
            if ErrCode == ErrorCode.Success:
                return ErrCode, NewestIndex
        return ErrCode, NewestIndex
    def __getNewestPostIndex(self, Board, ConnectIndex = 0):
        
        result = 0
        
        CatchList = [
            # 0
            '文章選讀',
        ]

        SendMessage = '\x1b[D\x1b[D\x1b[Dqs' + Board + '\r\x03\x03 0\r$'
        Refresh = True
        ExtraWait = 0

        ErrCode, CatchIndex = self.__operatePTT(ConnectIndex, SendMessage=SendMessage, CatchTargetList=CatchList, Refresh=Refresh, ExtraWait=ExtraWait)
        if ErrCode != ErrorCode.Success:
            return ErrCode, result

        # print(self.__ReceiveData[ConnectIndex])

        AllIndex = re.findall(r'\d+ ', self.__ReceiveData[ConnectIndex])
        
        if len(AllIndex) == 0:
            self.__showScreen(ErrCode, CatchIndex, ConnectIndex)
            return ErrorCode.UnknowError, result

        AllIndex = list(set(map(int, AllIndex)))

        AllIndex.sort(reverse=True)

        # print(AllIndex)

        for IndexTemp in AllIndex:
            # 確認是否連續 只有文章編號才可能連續
            isContinue = True

            for i in range(1, 3):
                if str(IndexTemp - i) not in self.__ReceiveData[ConnectIndex]:
                    isContinue = False
                    break
            
            if isContinue:
                result = IndexTemp
                break
        
        if result == 0:
            return ErrorCode.ParseError, result
        
        # 確認是否有因為上篇文章是數字結尾導致判斷錯誤的情況
        for i in range(1, 20):
            if str(result + 1) in self.__ReceiveData[ConnectIndex]:
                result += 1
            else: 
                break

        return ErrorCode.Success, result
    def post(self, Board, Title, Content, PostType, SignType):
        
        ConnectIndex = 0
        
        CatchList = [
            # 0
            '文章選讀',
        ]

        if '看板《' + Board + '》' in self.__ReceiveData[ConnectIndex] and '文章選讀' in self.__ReceiveData[ConnectIndex]:
            self.Log('已經位於 ' + Board + ' 板', LogLevel.DEBUG)
        else:
            # 前進至板面
            SendMessage = '\x1b[D\x1b[D\x1b[Dqs' + Board + '\r\x03\x03 '
            
            ErrCode, CatchIndex = self.__operatePTT(ConnectIndex, SendMessage=SendMessage, CatchTargetList=CatchList, Refresh=False)
            if ErrCode != ErrorCode.Success:
                return ErrCode

            if CatchIndex == -1:
                self.Log('前進至 ' + Board + '板失敗')
                print(self.__ReceiveData[ConnectIndex])
                return ErrorCode.UnknowError
        
        # 確認是否有發文權限

        CatchList = [
            # 0
            '或不選',
            # 1
            '使用者不可發言',
        ]

        SendMessage = '\x10'
        Refresh = False
        ExtraWait = 0

        Retry = False
        RetryCount = 0

        while True:
            
            if Retry:
                Retry = False
                RetryCount += 1
                if RetryCount == 3:
                    return ErrCode
            else:
                RetryCount = 0

            ErrCode, CatchIndex = self.__operatePTT(ConnectIndex, SendMessage=SendMessage, CatchTargetList=CatchList, Refresh=Refresh, ExtraWait=ExtraWait)
            if ErrCode != ErrorCode.Success:
                return ErrCode

            SendMessage = ' '
            Refresh = False
            ExtraWait = 0

            if CatchIndex == 0:
                self.Log('具備發文權限', LogLevel.DEBUG)
                break
            elif CatchIndex == 1:
                self.Log('你被水桶惹 QQ')
                return ErrorCode.NoPermission
            else:
                self.__showScreen(ErrCode, CatchIndex, ConnectIndex)
                return ErrorCode.UnknowError

        SendMessage = str(PostType) + '\r' + str(Title) + '\r' + str(Content) + '\x18'
        self.Log('送出文章', LogLevel.DEBUG)

        Refresh = True
        ExtraWait = 0

        CatchList = [
            # 0
            '確定要儲存檔案嗎',
        ]

        ErrCode, CatchIndex = self.__operatePTT(ConnectIndex, SendMessage=SendMessage, CatchTargetList=CatchList, Refresh=Refresh, ExtraWait=ExtraWait)
        if ErrCode != ErrorCode.Success:
            return ErrCode

        if CatchIndex == 0:
            self.Log('儲存檔案', LogLevel.DEBUG)
            SendMessage = 's\r'
        else:
            self.__showScreen(ErrCode, CatchIndex, ConnectIndex)
            return ErrorCode.UnknowError

        CatchList = [
            # 0
            '任意鍵繼續', 
            # 1
            'x=隨機', 
            # 2
            '文章選讀',
        ]
        
        Refresh = True
        ExtraWait = 0
        while True:
            ErrCode, CatchIndex = self.__operatePTT(ConnectIndex, SendMessage=SendMessage, CatchTargetList=CatchList, Refresh=Refresh, ExtraWait=ExtraWait)
            if ErrCode != ErrorCode.Success:
                return ErrCode

            if CatchIndex == 0:
                break
            elif CatchIndex == 1:
                self.Log('選擇簽名檔: ' + str(SignType), LogLevel.DEBUG)
                SendMessage = str(SignType) + '\r'
            elif CatchIndex == 2:
                break
            else:
                self.__showScreen(ErrCode, CatchIndex, ConnectIndex = ConnectIndex)
                return ErrorCode.UnknowError
        
        return ErrorCode.Success
    def __gotoPost(self, Board, PostIndex=0, PostID='', ConnectIndex=0):
        
        global ErrorCode

        PostIndex = int(PostIndex)
        PostID = str(PostID)

        if len(Board) == 0:
            return ErrorCode.ErrorInput

        if PostIndex != 0 and PostID != '':
            return ErrorCode.ErrorInput

        if PostIndex == 0 and PostID == '':
            return ErrorCode.ErrorInput

        ErrCode = self.__gotoBoard(Board, ConnectIndex)
        if ErrCode != ErrorCode.Success:
            self.Log('前進至 ' + Board + ' 板失敗 錯誤碼: ' + str(ErrCode), LogLevel.DEBUG)
            return ErrCode

        if self.__Cursor == '>':
            IndexTarget = '>{0: >6}'.format(str(PostIndex))
        else:
            IndexTargetTemp = str(PostIndex)
            if len(IndexTargetTemp) == 6:
                IndexTargetTemp = IndexTargetTemp[1:]
            IndexTarget = self.__Cursor + '{0: >5}'.format(IndexTargetTemp)
        
        CatchList = [
            # 0
            IndexTarget,
        ]
        if PostID != '':
            SendMessage = '#' + PostID + '\r'
        else:
            SendMessage = str(PostIndex) + '\r'

        Refresh = True
        ExtraWait = 0

        Retry = False
        RetryCount = 0
        while True:

            if Retry:
                Retry = False
                RetryCount += 1
                if RetryCount == 2:
                    return ErrCode
            else:
                RetryCount = 0

            ErrCode, CatchIndex = self.__operatePTT(ConnectIndex, SendMessage=SendMessage, CatchTargetList=CatchList, Refresh=Refresh, ExtraWait=ExtraWait)
            if ErrCode != ErrorCode.Success:
                return ErrCode

            SendMessage = ''
            Refresh = False
            ExtraWait = 0

            if CatchIndex == 0:
                for line in self.__ReceiveData[ConnectIndex].split('\n'):
                    if line.startswith(self.__Cursor):
                        if '□ (本文已被刪除)' in line[:self.width - 20]:
                            self.Log('文章已經被刪除: \r\n' + line[:self.width - 20])
                            return ErrorCode.PostDeleted
                        else:
                            break
                return ErrorCode.Success
            else:
                Retry = True
                ErrCode = ErrorCode.UnknowError
                continue

        return ErrorCode.UnknowError
    
    def push(self, Board, inputPushType, PushContent, PostID='', PostIndex=0):
        
        ConnectIndex=0
        
        PostIndex = int(PostIndex)
        PostID = str(PostID)

        if len(Board) == 0:
            self.Log('看板名稱輸入錯誤: ' + str(Board))
            return ErrorCode.ErrorInput

        if PostIndex != 0 and PostID != '':
            self.Log('文章編號與代碼輸入錯誤: 同時輸入')
            return ErrorCode.ErrorInput

        if PostIndex == 0 and PostID == '':
            self.Log('文章編號與代碼輸入錯誤: 皆無輸入')
            return ErrorCode.ErrorInput

        SendMessage = ''

        if '看板《' + Board + '》' in self.__ReceiveData[ConnectIndex] and '文章選讀' in self.__ReceiveData[ConnectIndex]:
            self.Log('已經位於 ' + Board + ' 板', LogLevel.DEBUG)
        else:
            # 前進至板面
            SendMessage += '\x1b[D\x1b[D\x1b[Dqs' + Board + '\r\x03\x03 '
        
        # 前進至文章

        if PostID != '':
            SendMessage += '#' + PostID + '\r'
        else:
            SendMessage += str(PostIndex) + '\r'

        # 查看是否具備推文權限
        SendMessage += 'X'

        CatchList = [
            # 0
            '您覺得這篇文章',
            # 1
            '禁止快速連續推文',
            # 2
            '禁止短時間內大量推文',
            # 3
            '使用者不可發言',
            # 4
            '加註方式',
            # 5
            '◆ 本文已刪除',
        ]

        ErrCode, CatchIndex = self.__operatePTT(ConnectIndex, SendMessage=SendMessage, CatchTargetList=CatchList, Refresh=True)
        if ErrCode != ErrorCode.Success:
            return ErrCode
        
        if CatchIndex == 0:
                
            self.Log('具備推文權限', LogLevel.DEBUG)

            if '值得推薦' in self.__ReceiveData[ConnectIndex]:
                Push = True
            else:
                Push = False

            if '給它噓聲' in self.__ReceiveData[ConnectIndex]:
                Boo = True
            else:
                Boo = False
            
            if '→註解' in self.__ReceiveData[ConnectIndex]:
                Arrow = True
            else:
                Arrow = False
            
            if inputPushType == PushType.Push:
                if not Push:
                    inputPushType = PushType.Arrow
            elif inputPushType == PushType.Boo:
                if not Boo:
                    inputPushType = PushType.Arrow
            elif inputPushType == PushType.Arrow:
                if not Arrow:
                    inputPushType = PushType.Push
            else:
                return ErrorCode.ErrorInput

            self.Log('準備推文')
            SendMessage = str(inputPushType) + str(PushContent) + '\ry\r'

        elif CatchIndex == 1:
            self.Log('禁止快速推文')
            return ErrorCode.NoFastPush
        elif CatchIndex == 2:
            self.Log('禁止機器人快速推文')
            return ErrorCode.NoFastPush
        elif CatchIndex == 3:
            self.Log('你被水桶惹 QQ')
            return ErrorCode.NoPermission
        elif CatchIndex == 4:
            self.Log('作者本人使用箭頭')
            SendMessage = str(PushContent) + '\ry\r'
        elif CatchIndex == 5:
            self.Log('文章已經被刪除')
            return ErrorCode.PostDeleted
        else:
            self.__showScreen(ErrCode, CatchIndex, ConnectIndex)
            return ErrorCode.UnknowError
        
        CatchList = []

        ErrCode, CatchIndex = self.__operatePTT(ConnectIndex, SendMessage=SendMessage, CatchTargetList=CatchList, Refresh=True)
        if ErrCode != ErrorCode.Success:
            return ErrCode

        # print(self.__ReceiveData[ConnectIndex])

        return ErrorCode.Success
    def getPostInfo(self, Board, PostID='', PostIndex=0):
        ConnectIndex = 0
        
        result = None
        
        PostIndex = int(PostIndex)
        PostID = str(PostID)

        if len(Board) == 0:
            self.Log('看板名稱輸入錯誤: ' + str(Board))
            return ErrorCode.ErrorInput, result

        if PostIndex != 0 and PostID != '':
            self.Log('文章編號與代碼輸入錯誤: 同時輸入')
            return ErrorCode.ErrorInput, result

        if PostIndex == 0 and PostID == '':
            self.Log('文章編號與代碼輸入錯誤: 皆無輸入')
            return ErrorCode.ErrorInput, result

        SendMessage = ''

        if '看板《' + Board + '》' in self.__ReceiveData[ConnectIndex] and '文章選讀' in self.__ReceiveData[ConnectIndex]:
            self.Log('已經位於 ' + Board + ' 板', LogLevel.DEBUG)
        else:
            # 前進至板面
            SendMessage += '\x1b[D\x1b[D\x1b[Dqs' + Board + '\r\x03\x03 '
        
        # 前進至文章

        if PostID != '':
            SendMessage += '#' + PostID + '\rQ'
        else:
            SendMessage += str(PostIndex) + '\rQ'

        CatchList = [
            # 0
            '找不到這個文章代碼',
            # 1
            '┌  ─  ─  ─  ─  ─  ─  ─  ─  ─  ─  ─  ─  ─  ─  ─  ─  ─  ─  ─  ─  ─  ─  ─  ─  ─  ─  ─  ─  ─  ─  ─  ─  ─  ─  ─  ─  ─  ┐',

        ]
        
        ErrCode, CatchIndex = self.__operatePTT(ConnectIndex, SendMessage=SendMessage, CatchTargetList=CatchList, Refresh=True)
        if ErrCode != ErrorCode.Success:
            return ErrCode, result

        # print(self.__ReceiveData[ConnectIndex])

        if CatchIndex == 0:
            self.Log('此文章代碼不存在')
            return ErrorCode.PostNotFound, result
        elif CatchIndex == 1:
            InformationEnd = '└  ─  ─  ─  ─  ─  ─  ─  ─  ─  ─  ─  ─  ─  ─  ─  ─  ─  ─  ─  ─  ─  ─  ─  ─  ─  ─  ─  ─  ─  ─  ─  ─  ─  ─  ─  ─  ─  ┘'
            screen = self.__ReceiveData[ConnectIndex]
            screen = screen[screen.find(CatchList[1]) + len(CatchList[1]):screen.find(InformationEnd)]

            screen = screen[screen.find('文章代碼(AID): #') + len('文章代碼(AID): #'):]
            if PostID == '':
                PostID = screen[:screen.find(' ')]

            PostTitle = screen[screen.find('ptt.cc') + len('ptt.cc') + 2:]
            PostTitle = PostTitle[:PostTitle.find('│')]
            while PostTitle.endswith(' ') or PostTitle.endswith('\r'):
                PostTitle = PostTitle[:-1]
            
            PostURL = screen[screen.find('https://www.ptt.cc/bbs'):]
            PostURL = PostURL[:PostURL.find(' ')]

            PostMoney = screen
            PostMoney = PostMoney[PostMoney.find('這一篇文章值'):]
            # 
            PostMoney = int(re.search(r'\d+', PostMoney).group())
            # print(screen)
        else:
            self.Log('文章已經被刪除')
            return ErrorCode.PostNotFound, result

        SendMessage = '\x03\r'

        CatchList = [
            # 0
            '目前顯示: 第',
        ]
        
        ErrCode, CatchIndex = self.__operatePTT(ConnectIndex, SendMessage=SendMessage, CatchTargetList=CatchList, Refresh=True)
        if ErrCode != ErrorCode.Success:
            return ErrCode, result

        if CatchIndex == 0:
            # print(self.__ReceiveData[ConnectIndex])
            # 
            PostAuthor = self.__ReceiveData[ConnectIndex]
            PostAuthor = PostAuthor[PostAuthor.find('[2J 作者  ') + len('[2J 作者  '):PostAuthor.find('看板  ' + Board)]
            while PostAuthor.endswith(' '):
                PostAuthor = PostAuthor[:-1]
            # 時間
            PostDate = self.__ReceiveData[ConnectIndex]
            PostDate = PostDate[PostDate.find(' 時間  ') + len(' 時間  '):]
            PostDate = PostDate[:24]

            PostContent = self.__ReceiveData[ConnectIndex]
            PostContentList = PostContent.split('\n')
            PostContentList = PostContentList[4:][:-1]
                
            if '※ 發信站: 批踢踢實業坊(ptt.cc), 來自:' in self.__ReceiveData[ConnectIndex]:
                PostIP = self.__ReceiveData[ConnectIndex]
                PostIP = PostIP[PostIP.find('※ 發信站: 批踢踢實業坊(ptt.cc), 來自: ') + len('※ 發信站: 批踢踢實業坊(ptt.cc), 來自: '):]
                PostIP = PostIP[:PostIP.find(' ')]
            
            PostContent = '\n'.join(PostContentList) + '\n'
            
            PushList = []
            PageIndex = 2
            LastPageIndex = [1, 22]
            PostContentAreaEnd = False

            while not '(100%)  目前顯示: 第' in self.__ReceiveData[ConnectIndex]:
                
                SendMessage = str(PageIndex) + '\r'
                CatchList = [
                    # 0
                    '目前顯示: 第',
                ]
                
                ErrCode, CatchIndex = self.__operatePTT(ConnectIndex, SendMessage=SendMessage, CatchTargetList=CatchList, Refresh=True)
                if ErrCode != ErrorCode.Success:
                    return ErrCode, result
                # print('-' * 50)
                # print(self.__ReceiveData[ConnectIndex])
                
                if CatchIndex == 0:
                    
                    PostContentTemp = self.__ReceiveData[ConnectIndex]
                    PostContentTemp = PostContentTemp.replace('[2J', '')
                    # while not PostContentTemp.startswith('推') and not PostContentTemp.startswith('→') and not PostContentTemp.startswith('噓'):
                    #     PostContentTemp = PostContentTemp[1:]

                    PostContentList = PostContentTemp.split('\n')
                    PostContentList = PostContentList[:-1]

                    PageLineRange = self.__ReceiveData[ConnectIndex]
                    PageLineRange = PageLineRange[PageLineRange.find('目前顯示: 第') + len('目前顯示: 第'):]
                    PageLineRange = re.findall(r'\d+', PageLineRange)
                    PageLineRange = list(map(int, PageLineRange))
                    # print('PageLineRange:', PageLineRange)
                    
                    OverlapLine = LastPageIndex[1] - PageLineRange[0] + 1

                    if OverlapLine >= 1:
                        # print('重疊', OverlapLine, '行')
                        PostContentList = PostContentList[OverlapLine:]

                    LastPageIndex = PageLineRange
                    PostContentTemp = ''
                    if '※ 發信站: 批踢踢實業坊(ptt.cc)' in self.__ReceiveData[ConnectIndex]:
                        
                        for line in PostContentList:
                            if not '※ 發信站: 批踢踢實業坊(ptt.cc)' in line:
                                PostContentTemp += line + '\n'
                            else:
                                break
                        PostContent += PostContentTemp
                        PostContentAreaEnd = True

                        PostIP = self.__ReceiveData[ConnectIndex]
                        PostIP = PostIP[PostIP.find('※ 發信站: 批踢踢實業坊(ptt.cc), 來自: ') + len('※ 發信站: 批踢踢實業坊(ptt.cc), 來自: '):]
                        PostIP = PostIP[:PostIP.find(' ')]
                        PostIP = PostIP.replace('\n', '')

                    elif not PostContentAreaEnd:
                        PostContent += '\n'.join(PostContentList) + '\n'

                    if PostContentAreaEnd:
                        for line in PostContentList:
                            while line.startswith(' '):
                                line = line[1:]
                            
                            CurrentPushType = 0

                            if line.startswith('推'):
                                CurrentPushType = PushType.Push
                            elif line.startswith('噓'):
                                CurrentPushType = PushType.Boo
                            elif line.startswith('→'):
                                CurrentPushType = PushType.Arrow
                                
                            if CurrentPushType != 0:
                                # print('Push line:' + line + '==end')
                                line = line[2:]

                                CurrentPushID = line[:line.find(':')]

                                line = line[line.find(':') + 2:]

                                CurrentPushTimeList = line.split(' ')
                                CurrentPushTime = CurrentPushTimeList.pop()
                                CurrentPushTime = CurrentPushTimeList.pop() + ' ' + CurrentPushTime

                                CurrentPushContent = ' '.join(CurrentPushTimeList)
                                while CurrentPushContent.endswith(' '):
                                    CurrentPushContent = CurrentPushContent[:-1]
                                
                                # print('Push Type:', CurrentPushType, '==end')
                                # print('Push ID:' + CurrentPushID + '==end')
                                # print('Push Content:' + CurrentPushContent + '==end')
                                # print('Push Time:' + CurrentPushTime + '==end')
                                # print('-' * 50)

                                CurrentPush = Information.PushInformation(CurrentPushType, CurrentPushID, CurrentPushContent, CurrentPushTime)
                                PushList.append(CurrentPush)
                PageIndex += 1
            
            while PostContent.startswith('\n'):
                PostContent = PostContent[1:]
            while PostContent.endswith('\n'):
                PostContent = PostContent[:-1]
                
        else:
            print(self.__ReceiveData[ConnectIndex])
            print('Catch error')

        print('PostID:', PostID)
        print('PostTitle:', PostTitle)
        print('PostURL:', PostURL)
        print('PostMoney:', PostMoney)
        print('PostAuthor:', PostAuthor)
        print('PostDate:', PostDate)
        print('PostContent:', PostContent + '=')
        print('PostIP:', PostIP + '=')
        # PostContent
        print('-' * 50)
        return ErrorCode.Success, result
    def __getPostinfoByUrl(self, WebUrl):
    
        self.Log('__getPostinfoByUrl: requests get', LogLevel.DEBUG)
        isError = False
        for i in range(600):
            try:
                res = requests.get(
                    url = WebUrl,
                    cookies={'over18': '1'},
                    timeout=3
                )
                isError = False
                break
            except requests.exceptions.Timeout:
                
                self.__MaxRequestCount -= 1
                if self.__MaxRequestCount < self.__MinRequestCount:
                    self.__MaxRequestCount = self.__MinRequestCount
                
                time.sleep(1)
                isError = True
            except requests.exceptions.ConnectionError:
                #self.Log('__getPostinfoByUrl: requests conect error', LogLevel.DEBUG)
                self.Log('__getPostinfoByUrl: requests conect error', LogLevel.DEBUG)
                time.sleep(1)
                isError = True
            except requests.exceptions.InvalidURL:
                self.Log('不合法的網址: ' + WebUrl, LogLevel.CRITICAL)
                return self.InvalidURLError, '', '', '', '', None, ''
            except requests.exceptions.MissingSchema:
                self.Log('不合法的網址: ' + WebUrl, LogLevel.CRITICAL)
                return self.InvalidURLError, '', '', '', '', None, ''
        if isError:
            self.Log('getPostinfoByUrl requests 超時!', LogLevel.CRITICAL)
            return self.WaitTimeout, '', '', '', '', None, ''
            
        soup =  BeautifulSoup(res.text, 'html.parser')
        main_content = soup.find(id='main-content')
        
        if main_content == None:
            return self.WebFormatError, '', '', '', '', None, ''

        metas = main_content.select('div.article-metaline')
        filtered = [ v for v in main_content.stripped_strings if v[0] not in ['※', '◆'] and  v[:2] not in ['--'] ]
        
        content = ' '.join(filtered)
        content = re.sub(r'(\s)+', '', content )

        try:
            author = metas[0].select('span.article-meta-value')[0].string
            title = metas[1].select('span.article-meta-value')[0].string
            date = metas[2].select('span.article-meta-value')[0].string
        except IndexError:
            self.Log('div.article-metaline is not exist', LogLevel.DEBUG)
            return self.WebFormatError, '', '', '', '', None, ''
        RealPostTitle = title
        RealPostAuthor = author
        RealPostDate = date
        RealPostContent = ''
        PostContentArea = False
        
        PushArea = False
        
        PushType = 0
        PushID = ''
        PushContent = ''
        PushDate = ''
        PushIndex = 0
        
        RealPushList = []
        for ContentLine in filtered:
            self.Log('ContentLine-> ' + ContentLine, LogLevel.DEBUG)
            if not PostContentArea and (ContentLine.startswith('推') or ContentLine.startswith('噓') or ContentLine.startswith('→')):
                PushArea = True
                PushIndex = 0
            if PushArea:
                if PushIndex == 0:
                    if '推' in ContentLine:
                        PushType = self.PushType_Push
                    elif '噓' in ContentLine:
                        PushType = self.PushType_Boo
                    elif '→' in ContentLine:
                        PushType = self.PushType_Arrow
                    self.Log('PushType-> ' + str(PushType), LogLevel.DEBUG)
                if PushIndex == 1:
                    PushID = ContentLine
                if PushIndex == 2:
                    PushContent = ContentLine[2:]
                if PushIndex == 3:
                    PushDate = ContentLine
                    PushArea = False
                PushIndex += 1
                
                if PushIndex >=4:
                    PushIndex = 0
                    self.Log('Push final-> ' + str(PushType) + ' ' + PushID + ' ' + PushContent + ' ' + PushDate, LogLevel.DEBUG)
                    RealPushList.append(PushInformation(PushType, PushID, PushContent, PushDate))
            if date in ContentLine:
                PostContentArea = True
                continue
            if WebUrl in ContentLine:
                PostContentArea = False
            if PostContentArea:
                RealPostContent += ContentLine + '\r'
        
        return ErrorCode.Success, RealPostTitle, RealPostAuthor, RealPostDate, RealPostContent, RealPushList, res.text
    
    def __parsePost(self, ConnectIndex = 0):
        RealPostID = ''
        RealWebUrl = ''
        RealMoney = -1
        ErrCode = ErrorCode.Success
        
        #┌─────────────────────────────────────┐
        #└─────────────────────────────────────┘
        
        self.Log(self.__ReceiveData[ConnectIndex], LogLevel.DEBUG)

        if not '┌─────────────────────────────────────┐' in self.__ReceiveData[ConnectIndex] or not '└─────────────────────────────────────┘' in self.__ReceiveData[ConnectIndex]:
            return self.ParseError, RealPostID, RealMoney, RealWebUrl
        
        self.__ReceiveData[ConnectIndex] = self.__ReceiveData[ConnectIndex][self.__ReceiveData[ConnectIndex].find('┌─────────────────────────────────────┐') : self.__ReceiveData[ConnectIndex].find('└─────────────────────────────────────┘')]
        
        if '#' in self.__ReceiveData[ConnectIndex]:
            RealPostID = self.__ReceiveData[ConnectIndex][self.__ReceiveData[ConnectIndex].find('#') + 1:]
            RealPostID = RealPostID[:RealPostID.find(' ')]
        else:
            self.Log('解析文章代碼失敗', LogLevel.DEBUG)
            ErrCode = self.ParseError
            
        if 'https' in self.__ReceiveData[ConnectIndex]:
            RealWebUrl = self.__ReceiveData[ConnectIndex][self.__ReceiveData[ConnectIndex].find('https://www.ptt.cc/bbs'):]
            
            self.Log(self.__ReceiveData[ConnectIndex], LogLevel.DEBUG)
            self.Log(RealWebUrl, LogLevel.DEBUG)
            
            RealWebUrl = RealWebUrl[RealWebUrl.find('https'):RealWebUrl.find('.html') + 5]
            
            self.Log('QQ ' + RealWebUrl, LogLevel.DEBUG)
        else:
            self.Log('解析文章網址失敗', LogLevel.DEBUG)
            ErrCode = self.ParseError
            
        if '這一篇文章值' in self.__ReceiveData[ConnectIndex]:
            RealMoneyTemp = self.__ReceiveData[ConnectIndex][self.__ReceiveData[ConnectIndex].find('這一篇文章值') + len('這一篇文章值') : self.__ReceiveData[ConnectIndex].find('Ptt幣')]
            RealMoney = int(re.search(r'\d+', RealMoneyTemp).group())
        else:
            self.Log('解析文章價錢失敗', LogLevel.DEBUG)
            ErrCode = self.ParseError
        
        if ErrCode != ErrorCode.Success:
            return ErrCode, RealPostID, RealMoney, RealWebUrl
            
        return ErrorCode.Success, RealPostID, RealMoney, RealWebUrl
    def __getPostInfoByID(self, Board, PostID, Index=-1, ConnectIndex = 0):
        self.Log('Into __getPostInfoByID', LogLevel.DEBUG)
        if Index != -1:
            self.Log('Into __gotoPostByIndex', LogLevel.DEBUG)
            ErrCode = self.__gotoPostByIndex(Board, Index, ConnectIndex)
            if ErrCode != ErrorCode.Success:
                self.Log('getPostInfoByIndex 1 goto post fail', LogLevel.DEBUG)
                return ErrCode, None
        else:
            self.Log('Into __gotoPostByID', LogLevel.DEBUG)
            if len(PostID) != 8:
                self.Log('Error input: ' + PostID)
                return self.ErrorInput, None
        
            ErrCode = self.__gotoPostByID(Board, PostID, ConnectIndex)
            if ErrCode != ErrorCode.Success:
                self.Log('getPostInfoByID 1 goto post fail', LogLevel.DEBUG)
                return ErrCode, None
        
        ErrCode, Index = self.__readScreen(ConnectIndex, 'Q', ['請按任意鍵繼續'])
        if ErrCode == self.WaitTimeout:
            return self.PostDeleted, None
        if ErrCode != ErrorCode.Success:
            self.Log('getPostInfoByID 3 read screen error: ' + str(ErrorCode), LogLevel.DEBUG)
            return ErrCode, None
        
        ErrCode, RealPostID, RealMoney, RealWebUrl = self.__parsePost(ConnectIndex)
        
        while self.__RequestCount >= self.__MaxRequestCount:
            time.sleep(0.1)
        
        self.__RequestCount += 1
        ErrCode, RealPostTitle, RealPostAuthor, RealPostDate, RealPostContent, RealPushList, OriginalText = self.__getPostinfoByUrl(RealWebUrl)
        self.__RequestCount -= 1
        
        if ErrCode != ErrorCode.Success:
            self.Log('連線頻道 ' + str(ConnectIndex) + ' 取得文章失敗', LogLevel.DEBUG)
            return ErrCode, None
        
        result = PostInformation(Board, RealPostID, RealPostAuthor, RealPostDate, RealPostTitle, RealWebUrl, RealMoney, RealPostContent, RealPushList, OriginalText)
        
        return ErrorCode.Success, result
        
    def crawlSaveThread(self, ThreadIndex, Board):
        
        self.Log('線程 ' + str(ThreadIndex) + ' 啟動', LogLevel.DEBUG)
        
        while True:
            
            if self.__ConnectCount == 0:
                if len(self.__CrawPool) == 0:
                    break
            
            self.__CrawPoolLock.acquire()
            if len(self.__CrawPool) == 0:
                self.__CrawPoolLock.release()
                time.sleep(0.1)
                continue
                
            Index, RealPostID, RealMoney, RealWebUrl = self.__CrawPool.pop()
            self.__CrawPoolLock.release()
            
            self.Log('線程 ' + str(ThreadIndex) + ' 取得編號 ' + str(Index) + ' ' + RealWebUrl, LogLevel.DEBUG)
            
            ErrCode, RealPostTitle, RealPostAuthor, RealPostDate, RealPostContent, RealPushList, OriginalText = self.__getPostinfoByUrl(RealWebUrl)
            
            if ErrCode != ErrorCode.Success:
                self.Log('線程 ' + str(ThreadIndex) + ' 取得文章失敗', LogLevel.DEBUG)
                if not self.__isBackground and self.__ShowProgressBar:
                    self.__ProgressBarCount += 1
                    self.__ProgressBar.update(self.__ProgressBarCount)
                continue
            #Find post
            
            Post = PostInformation(Board, RealPostID, RealPostAuthor, RealPostDate, RealPostTitle, RealWebUrl, RealMoney, RealPostContent, RealPushList, OriginalText)
            
            if not self.__isBackground and self.__ShowProgressBar:
                self.__ProgressBarCount += 1
                self.__ProgressBar.update(self.__ProgressBarCount)
            self.__SuccessPostCount += 1
            self.__PostHandler(Post)
        
        self.__SaveCount -= 1
        self.Log('線程 ' + str(ThreadIndex) + ' 結束', LogLevel.DEBUG)
        
    def crawlFindUrlThread(self, Board, StartIndex , EndIndex, ConnectIndex):
        
        self.Log('連線頻道 ' + str(ConnectIndex) + ' 開始取得編號 ' + str(StartIndex) + ' 到 ' + str(EndIndex) + ' 文章網址')
        
        for Index in range(StartIndex, EndIndex + 1):
        
            isSuccess = False
            FailReason = ''
            for i in range(3):
                ErrCode = self.__gotoPostByIndex(Board, Index, ConnectIndex)
                
                if ErrCode != ErrorCode.Success:
                    FailReason = '連線頻道 ' + str(ConnectIndex) + ' crawlFindUrlThread 1 goto post fail'
                    continue
                
                ErrCode, ScreenIndex = self.__readScreen(ConnectIndex, 'Q', ['請按任意鍵繼續'])

                if ErrCode == self.WaitTimeout:
                    FailReason = '連線頻道 ' + str(ConnectIndex) + ' 讀取畫面超時'
                    continue
                if ErrCode != ErrorCode.Success:
                    FailReason = '連線頻道 ' + str(ConnectIndex) + ' crawlFindUrlThread 3 __readScreen error: ' + str(ErrorCode)
                    break
                    
                ErrCode, RealPostID, RealMoney, RealWebUrl = self.__parsePost(ConnectIndex)
                if ErrCode != ErrorCode.Success:
                    FailReason = '連線頻道 ' + str(ConnectIndex) + ' 解析文章失敗'
                    continue
                    
                isSuccess = True
                break
            
            if not isSuccess:
                self.Log(FailReason, LogLevel.DEBUG)
                if not self.__isBackground and self.__ShowProgressBar:
                    self.__ProgressBarCount += 1
                    self.__ProgressBar.update(self.__ProgressBarCount)
                continue
                
            if RealWebUrl != '':
                # Get RealWebUrl!!!
                #self.Log(str(len(self.__CrawPool)))
                #self.Log('連線頻道 ' + str(ConnectIndex) + ' : ' + RealWebUrl)
                self.__CrawPool.append((Index, RealPostID, RealMoney, RealWebUrl))
            
        self.Log('連線頻道 ' + str(ConnectIndex) + ' 結束', LogLevel.DEBUG)
        self.__ConnectCount -= 1
        
    def crawlBoard(self, Board, PostHandler, StartIndex=0, EndIndex=0, ShowProgressBar=True):
    
        self.__PostHandler = PostHandler
    
        DefaultThreadNumber = 32
        
        self.Log('Into crawlBoard', LogLevel.DEBUG)
        
        self.__ShowProgressBar = ShowProgressBar
        
        if StartIndex == 0 and EndIndex == 0:
            self.Log('爬行 ' + Board + ' 板所有文章')
            
            ErrCode, EndIndex = self.getNewestPostIndex(Board)
            if ErrCode == ErrorCode.Success:
                #self.Log('Get ' + Board + ' get newest post index success: ' + str(EndIndex))
                pass
            else:
                self.Log('取得' + Board + '板最新文章編號錯誤')
                return self.UnknowError
            
        if EndIndex < StartIndex:
            self.Log('文章編號範圍錯誤: ' + str(StartIndex) + ' 到 ' + str(EndIndex))
            return self.ErrorInput
        
        ConnectList = [0]
        self.__CrawPoolLock = threading.Lock()
        self.__TotalPost = EndIndex - StartIndex + 1

        if not self.__isBackground and self.__ShowProgressBar:
            self.__ProgressBar = progressbar.ProgressBar(max_value=self.__TotalPost)
            self.__ProgressBarCount = 0
        self.__SuccessPostCount = 0
        
        self.__RequestCount = 0
        self.__MaxRequestCount = DefaultThreadNumber
        self.__MinRequestCount = 4
        
        self.__ThreadLock = None
        
        if self.__MaxMultiLogin > 1 and EndIndex - StartIndex + 1 > 10:
            self.__kickOtherLogin = False
            self.Log('啟動多重登入模式')
            for i in range(1, self.__MaxMultiLogin):
                for ii in range(3):            
                    if self.__connectRemote(i) == ErrorCode.Success:
                        ConnectList.append(i)
                        break
        else:
            self.Log('啟動單一登入模式')

        ConnectListTemp = ''
        
        for ConnectIndex in ConnectList:
            ConnectListTemp += str(ConnectIndex) + ' '
        self.Log('已啟動連線 ' + ConnectListTemp)
        
        if StartIndex == 0:
            StartIndex = 1
        self.Log('開始爬行 ' + Board + ' 板編號 ' + str(StartIndex) + ' 到 ' + str(EndIndex) + ' 的文章')

        ThreadUnit = int((EndIndex - StartIndex) / len(ConnectList))
        
        self.Log('總共 ' + str(self.__TotalPost) + ' 篇文章')
        
        self.__ConnectCount = len(ConnectList)
        self.__SaveCount = DefaultThreadNumber
        
        ThreadUnitCount = 0
        
        self.__CurrentLogLevel = self.__LogLevel
        
        self.setLogLevel(LogLevel.CRITICAL)
        
        for ConnectIndex in ConnectList:
        
            ThreadStartIndex = 0
            ThreadEndIndex = 0

            if len(ConnectList) == 1:
                ThreadStartIndex = StartIndex
                ThreadEndIndex = EndIndex
            elif ThreadUnitCount == 0:

                ThreadStartIndex = StartIndex
                ThreadEndIndex = StartIndex + ThreadUnit
                
            elif ConnectIndex == ConnectList[len(ConnectList) - 1]:
                
                ThreadStartIndex = StartIndex + ThreadUnitCount * ThreadUnit + 1
                ThreadEndIndex = EndIndex
            else:

                ThreadStartIndex = StartIndex + ThreadUnitCount * ThreadUnit + 1
                ThreadEndIndex = StartIndex + (ThreadUnitCount + 1) * ThreadUnit

            # print('ThreadStartIndex: ' + str(ThreadStartIndex))
            # print('ThreadEndIndex: ' + str(ThreadEndIndex))
            
            threading.Thread(target = self.crawlFindUrlThread, args = (Board, ThreadStartIndex, ThreadEndIndex, ConnectIndex) ).start()
            
            ThreadUnitCount += 1
        
        for ConnectIndex in range(DefaultThreadNumber):
            threading.Thread(target = self.crawlSaveThread, args = (ConnectIndex, Board)).start()

        while True:
            time.sleep(1)
            if self.__ConnectCount == 0:
                if len(self.__CrawPool) == 0 and self.__SaveCount == 0:
                    if not self.__isBackground and self.__ShowProgressBar:
                        self.__ProgressBar.update(self.__TotalPost)
                        self.__ProgressBar.finish()
                    break

        for ConnectIndex in ConnectList:
            if ConnectIndex != 0:
                self.logout(ConnectIndex)
        
        self.__LogLevel = self.__CurrentLogLevel
        
        self.Log('成功取得 ' + str(self.__SuccessPostCount) + ' 篇文章')
        
        return ErrorCode.Success
    def getPostInfoByIndex(self, Board, Index, ConnectIndex = 0):
        
        ErrCode, Post = self.getPostInfoByID(Board, '', Index, ConnectIndex)
        
        return ErrCode, Post
    
    def getNewPostIndexList(self, Board, LastPostIndex, ConnectIndex = 0):
        
        result = []
        ErrCode, LastIndex = self.getNewestPostIndex(Board, ConnectIndex)

        if ErrCode != ErrorCode.Success:
            return ErrCode, result
        
        if LastPostIndex <= 0 or LastIndex < LastPostIndex:
            result.append(LastIndex)
        else:
            for IndexTemp in range(LastPostIndex + 1, LastIndex + 1):
                result.append(IndexTemp)
        return ErrCode, result
    
    def pushByID(self, Board, PushType, PushContent, PostID, PostIndex=-1, ConnectIndex = 0):
    
        for i in range(5):
            ErrCode = self.__pushByID(Board, PushType, PushContent, PostID, PostIndex, ConnectIndex)
            if ErrCode == ErrorCode.Success:
                if i != 0:
                    self.Log('pushByID recover Success', LogLevel.DEBUG)
                break
            if ErrCode == self.NoPermission:
                break
        return ErrorCode
    def __pushByID(self, Board, PushType, PushContent, PostID, PostIndex=-1, ConnectIndex = 0):
        self.__CurrentTimeout[ConnectIndex] = 3

        if PostIndex != -1:
            ErrCode = self.__gotoPostByIndex(Board, PostIndex, ConnectIndex)
            if ErrCode != ErrorCode.Success:
                self.Log('pushByIndex 1 goto post fail', LogLevel.DEBUG)
                return ErrorCode
        else:
        
            if len(PostID) != 8:
                self.Log('pushByID Error input: ' + PostID)
                return self.ErrorInput
        
            ErrCode = self.__gotoPostByID(Board, PostID, ConnectIndex)
            if ErrCode != ErrorCode.Success:
                self.Log('pushByID 1 goto post fail', LogLevel.DEBUG)
                return ErrorCode

        Message = 'X'
        
        while True:
        
            ErrCode, Index = self.__readScreen(ConnectIndex, Message, ['您覺得這篇文章', '加註方式', '禁止快速連續推文', '禁止短時間內大量推文', '使用者不可發言'])
            if ErrCode == self.WaitTimeout:
                print(self.__ReceiveData[ConnectIndex])
                self.Log('No push option')
                return self.NoPermission
            if ErrCode != ErrorCode.Success:
                self.Log('pushByID 2 error code: ' + str(ErrorCode), LogLevel.DEBUG)
                return ErrorCode
            
            Pushable = False
            
            ArrowOnly = False
            
            AllowPushTypeList = [False, False, False, False]
            
            AllowPushTypeList[self.PushType_Push] = False
            AllowPushTypeList[self.PushType_Boo] = False
            AllowPushTypeList[self.PushType_Arrow] = False
            
            if Index == 0:
                if '值得推薦' in self.__ReceiveData[ConnectIndex]:
                    AllowPushTypeList[self.PushType_Push] = True
                if '給它噓聲' in self.__ReceiveData[ConnectIndex]:
                    AllowPushTypeList[self.PushType_Boo] = True
                if '註解' in self.__ReceiveData[ConnectIndex]:
                    AllowPushTypeList[self.PushType_Arrow] = True
                Pushable = True
                break
            if Index == 1:
                AllowPushTypeList[self.PushType_Arrow] = True
                PushType = self.PushType_Arrow
                ArrowOnly = True
                Pushable = True
                break
            if Index == 2:
                self.Log('無法快速推文，等待中...')
                Message = 'qX'
                time.sleep(1)
            if Index == 3:
                self.Log('系統阻擋過多推文，等待中...')
                Message = 'qX'
                time.sleep(2)
            if Index == 4:
                self.Log('你被水桶惹 QQ')
                return self.NoPermission
                
        if not AllowPushTypeList[self.PushType_Boo] and PushType == self.PushType_Boo:
            PushType = self.PushType_Arrow
        
        CaseList = ['']
        
        if ArrowOnly:
            SendMessage = PushContent + '\ry'
        else:
            SendMessage = str(PushType) + PushContent + '\ry'
        
        ErrCode, Index = self.__sendData(ConnectIndex, SendMessage, CaseList, True, True)
        if ErrCode != ErrorCode.Success:
            self.Log('pushByID 3 error code: ' + str(ErrorCode), LogLevel.DEBUG)
            return ErrorCode

        return ErrorCode.Success
    def pushByIndex(self, Board, PushType, PushContent, PostIndex, ConnectIndex = 0):
        ErrCode = self.pushByID(Board, PushType, PushContent, '', PostIndex, ConnectIndex)
        return ErrorCode
    def mail(self, UserID, MailTitle, MailContent, SignType, ConnectIndex = 0):
    
        ErrCode = self.__gotoTop(ConnectIndex)
        if ErrCode != ErrorCode.Success:
            print('mail goto top error code 1: ' + str(ErrorCode))
            return ErrorCode
        
        CaseList = ['主題：', '請選擇簽名檔', '已順利寄出，是否自存底稿', '任意鍵繼續', '電子郵件']
        SendMessage = 'M\rS\r' + UserID
        Enter = True
        while True:
            ErrCode, Index = self.__sendData(ConnectIndex, SendMessage, CaseList, Enter)
            if ErrCode == self.WaitTimeout:
                self.__showScreen()
                self.Log('無該使用: ' + UserID)
                return self.NoUser
            if ErrCode != ErrorCode.Success:
                self.Log('mail 2 error code: ' + str(ErrorCode), LogLevel.DEBUG)
                return ErrorCode
            if Index == 0:
                SendMessage = MailTitle + '\r' + MailContent + '\x18s'
                Enter = True
                self.__CurrentTimeout[ConnectIndex] = 3
                self.Log('mail 主題', LogLevel.DEBUG)
            if Index == 1:
                SendMessage = str(SignType)
                Enter = True
                self.Log('mail 請選擇簽名檔', LogLevel.DEBUG)
            if Index == 2:
                SendMessage = 'Y'
                Enter = True
                self.Log('mail 已順利寄出', LogLevel.DEBUG)
            if Index == 3:
                SendMessage = 'q'
                Enter = False
                self.Log('mail 任意鍵繼續', LogLevel.DEBUG)
            if Index == 4:
                self.Log('mail 回到電子郵件', LogLevel.DEBUG)
                break
        
        return ErrorCode.Success
        
    def giveMoney(self, ID, Money, YourPassword, ConnectIndex = 0):
        self.__CurrentTimeout[ConnectIndex] = 3
        
        ErrCode = self.__gotoTop(ConnectIndex)
        if ErrCode != ErrorCode.Success:
            print('giveMoney goto top error code 1: ' + str(ErrorCode))
            return ErrorCode
        
        CaseList = ['量販店', '給其他人Ptt幣', '這位幸運兒的id', '請輸入金額', '請輸入您的密碼', '要修改紅包袋嗎', '確定進行交易嗎', '按任意鍵繼續']
        SendMessage = 'P'
        Enter = True
        while True:        
            ErrCode, Index = self.__sendData(ConnectIndex, SendMessage, CaseList, Enter)
            if ErrCode == self.WaitTimeout:
                self.__showScreen()
                self.Log('No such option: ' + SendMessage, LogLevel.DEBUG)
                return self.NoUser
            if ErrCode != ErrorCode.Success:
                self.Log('mail 2 error code: ' + str(ErrorCode), LogLevel.DEBUG)
                return ErrorCode
            if Index == 0:
                SendMessage = 'P'
                Enter = True
                self.Log('giveMoney 量販店', LogLevel.DEBUG)
            if Index == 1:
                SendMessage = '0'
                Enter = True
                self.Log('giveMoney 給其他人Ptt幣', LogLevel.DEBUG)
            if Index == 2:
                SendMessage = ID
                Enter = True
                self.Log('giveMoney 這位幸運兒的id', LogLevel.DEBUG)
            if Index == 3:
                SendMessage = '\t' + str(Money)
                Enter = True
                self.Log('giveMoney 請輸入金額', LogLevel.DEBUG)
            if Index == 4:
                SendMessage = str(YourPassword)
                Enter = True
                self.__CurrentTimeout[ConnectIndex] = 3
                self.Log('giveMoney 請輸入您的密碼', LogLevel.DEBUG)
            if Index == 5:
                SendMessage = 'n'
                Enter = True
                self.__CurrentTimeout[ConnectIndex] = 3
                self.Log('giveMoney 要修改紅包袋嗎', LogLevel.DEBUG)
            if Index == 6:
                SendMessage = 'y'
                Enter = True
                self.__CurrentTimeout[ConnectIndex] = 3
                self.Log('giveMoney 確定進行交易嗎', LogLevel.DEBUG)
            if Index == 7:
                self.Log('giveMoney 按任意鍵繼續', LogLevel.DEBUG)
                break
        return ErrorCode.Success
        
    def getTime(self, ConnectIndex = 0):
        for i in range(10):
            ErrCode, Time = self.__getTime(ConnectIndex)
            if ErrCode == ErrorCode.Success:
                if i != 0:
                    self.Log('getTime recover Success ' + str(i) + ' times', LogLevel.DEBUG)
                break
        
        if len(Time) == 4:
            Time = '0' + Time
        
        return ErrCode, Time
    def __getTime(self, ConnectIndex = 0):
        self.__CurrentTimeout[ConnectIndex] = 2
        
        #Thanks for ervery one in Python
        
        ErrCode = self.__gotoTop(ConnectIndex)
        if ErrCode != ErrorCode.Success:
            print('getTime goto top error code 2: ' + str(ErrorCode))
            return ErrCode, ''
        
        for i in range(3):
            self.__CurrentTimeout[ConnectIndex] = 5
            ErrCode, Index = self.__readScreen(ConnectIndex, 'A\rqA\rq', ['呼叫器'])
            if ErrCode == self.WaitTimeout:
                self.Log(self.__ReceiveData[ConnectIndex], LogLevel.DEBUG)
                self.Log('getTime 2.1', LogLevel.DEBUG)
                #return ErrCode, ''
            if ErrCode != ErrorCode.Success:
                self.Log('getTime 3 read screen error code: ' + str(ErrorCode), LogLevel.DEBUG)
                #return ErrCode, ''
            if '離開，再見…' in self.__ReceiveData[ConnectIndex] and '呼叫器' in self.__ReceiveData[ConnectIndex] and '星期' in self.__ReceiveData[ConnectIndex]:
                break
        if not '離開，再見…' in self.__ReceiveData[ConnectIndex] or not '呼叫器' in self.__ReceiveData[ConnectIndex] or not '星期' in self.__ReceiveData[ConnectIndex]:
            return self.ParseError, ''
        
        LastResult = self.__ReceiveData[ConnectIndex]
        
        result = self.__ReceiveData[ConnectIndex][self.__ReceiveData[ConnectIndex].find('離開，再見…') + len('離開，再見…'):self.__ReceiveData[ConnectIndex].find('呼叫器')]
        
        if result.find('星期') < 0:
            self.Log(LastResult, LogLevel.DEBUG)
            self.Log(result, LogLevel.DEBUG)
            self.Log('無法取得時間標的', LogLevel.DEBUG)
            return self.ParseError, ''
            
        result = result[result.find('星期') + len('星期'):]
        result = result[result.find(' ') + 1:result.find(']')]

        return ErrorCode.Success, result
    
    def getUserInfo(self, ID, ConnectIndex = 0):
        ErrCode = self.__gotoTop(ConnectIndex)
        if ErrCode != ErrorCode.Success:
            print('getUserInfo goto top error code 1: ' + str(ErrorCode))
            return ErrCode, None
        CaseList = ['請輸入使用者代號', '請按任意鍵繼續', '顯示上幾次熱訊']
        SendMessage = 'T\rQ\r'
        Enter = False
        while True:        
            ErrCode, Index = self.__sendData(ConnectIndex, SendMessage, CaseList, Enter)
            if ErrCode == self.WaitTimeout:
                self.__showScreen()
                self.Log('No such option: ' + SendMessage, LogLevel.DEBUG)
                return ErrCode, None
            if ErrCode != ErrorCode.Success:
                self.Log('getUserInfo 2 error code: ' + str(ErrorCode), LogLevel.DEBUG)
                return ErrCode, None
            if Index == 0:
                #self.Log('Input user ID')
                SendMessage = str(ID)
                Enter = True
            if Index == 1:
                break
            if Index == 2:
                #self.Log('No such user')
                return self.NoUser, None
        
                
        self.__CurrentTimeout[ConnectIndex] = 3
        
        ErrCode, Index = self.__readScreen(ConnectIndex, '', ['請按任意鍵繼續'])
        
        if ErrCode == self.WaitTimeout:
            return self.WaitTimeout, None
        if ErrCode != ErrorCode.Success:
            self.Log('getUserInfo 3 read screen time out', LogLevel.DEBUG)
            return ErrCode, None
        
        if not '《ＩＤ暱稱》' in self.__ReceiveData[ConnectIndex] or not '《經濟狀況》' in self.__ReceiveData[ConnectIndex] or not '《登入次數》' in self.__ReceiveData[ConnectIndex] or not '《有效文章》' in self.__ReceiveData[ConnectIndex] or not '《目前動態》' in self.__ReceiveData[ConnectIndex] or not '《私人信箱》' in self.__ReceiveData[ConnectIndex] or not '《上次上站》' in self.__ReceiveData[ConnectIndex] or not '《上次故鄉》' in self.__ReceiveData[ConnectIndex] or not '《 五子棋 》' in self.__ReceiveData[ConnectIndex] or not '《象棋戰績》' in self.__ReceiveData[ConnectIndex]:
            self.Log('User info not complete')
            return self.WaitTimeout, None
        #print(self.__ReceiveData[ConnectIndex])
        
        UserID = self.__ReceiveData[ConnectIndex][self.__ReceiveData[ConnectIndex].find('《ＩＤ暱稱》') + len('《ＩＤ暱稱》'):self.__ReceiveData[ConnectIndex].find(')') + 1]
        self.__ReceiveData[ConnectIndex] = self.__ReceiveData[ConnectIndex][self.__ReceiveData[ConnectIndex].find(')') + 1:]
        
        Temp = self.__ReceiveData[ConnectIndex][:self.__ReceiveData[ConnectIndex].find('《登入次數》')]

        UserMoney = self.__ReceiveData[ConnectIndex][self.__ReceiveData[ConnectIndex].find('《經濟狀況》') + len('《經濟狀況》'):self.__ReceiveData[ConnectIndex].find('《登入次數》')]
        
        while UserMoney.endswith('m') or UserMoney.endswith(' ') or UserMoney.endswith('[') or UserMoney.endswith('\r') or UserMoney.endswith('\n') or UserMoney.endswith('\x1B'):
            UserMoney = UserMoney[:len(UserMoney) - 1]
        
        self.__ReceiveData[ConnectIndex] = self.__ReceiveData[ConnectIndex][self.__ReceiveData[ConnectIndex].find('《登入次數》'):]

        UserLoginTime = self.__ReceiveData[ConnectIndex][self.__ReceiveData[ConnectIndex].find('《登入次數》') + len('《登入次數》'):self.__ReceiveData[ConnectIndex].find(')') + 1]
        UserLoginTime = int(re.search(r'\d+', UserLoginTime).group())
        self.__ReceiveData[ConnectIndex] = self.__ReceiveData[ConnectIndex][self.__ReceiveData[ConnectIndex].find(')') + 1:]
        
        UserPost = self.__ReceiveData[ConnectIndex][self.__ReceiveData[ConnectIndex].find('《有效文章》') + len('《有效文章》'):self.__ReceiveData[ConnectIndex].find(')') + 1]
        UserPost = int(re.search(r'\d+', UserPost).group())
        self.__ReceiveData[ConnectIndex] = self.__ReceiveData[ConnectIndex][self.__ReceiveData[ConnectIndex].find(')') + 1:]
        
        UserState = self.__ReceiveData[ConnectIndex][self.__ReceiveData[ConnectIndex].find('《目前動態》') + len('《目前動態》'):self.__ReceiveData[ConnectIndex].find('《私人信箱》')]
        
        while UserState.endswith('m') or UserState.endswith(' ') or UserState.endswith('[') or UserState.endswith('\r') or UserState.endswith('\n') or UserState.endswith('\x1B'):
            UserState = UserState[:len(UserState) - 1]
        
        self.__ReceiveData[ConnectIndex] = self.__ReceiveData[ConnectIndex][self.__ReceiveData[ConnectIndex].find('《私人信箱》'):]
        
        UserMail = self.__ReceiveData[ConnectIndex][self.__ReceiveData[ConnectIndex].find('《私人信箱》') + len('《私人信箱》'):self.__ReceiveData[ConnectIndex].find('《上次上站》')]
        
        while UserMail.endswith('m') or UserMail.endswith(' ') or UserMail.endswith('[') or UserMail.endswith('\r') or UserMail.endswith('\n') or UserMail.endswith('\x1B'):
            UserMail = UserMail[:len(UserMail) - 1]
        
        self.__ReceiveData[ConnectIndex] = self.__ReceiveData[ConnectIndex][self.__ReceiveData[ConnectIndex].find('《上次上站》'):]
        
        UserLastLogin = self.__ReceiveData[ConnectIndex][self.__ReceiveData[ConnectIndex].find('《上次上站》') + len('《上次上站》'):self.__ReceiveData[ConnectIndex].find('《上次故鄉》')]
        
        while UserLastLogin.endswith('m') or UserLastLogin.endswith(' ') or UserLastLogin.endswith('[') or UserMail.endswith('\r') or UserMail.endswith('\n') or UserMail.endswith('\x1B'):
            UserLastLogin = UserLastLogin[:len(UserLastLogin) - 1]
        
        self.__ReceiveData[ConnectIndex] = self.__ReceiveData[ConnectIndex][self.__ReceiveData[ConnectIndex].find('《上次故鄉》'):]
        
        UserLastIP = self.__ReceiveData[ConnectIndex][self.__ReceiveData[ConnectIndex].find('《上次故鄉》') + len('《上次故鄉》'):self.__ReceiveData[ConnectIndex].find('《 五子棋 》')]
        
        while UserLastIP.endswith('m') or UserLastIP.endswith(' ') or UserLastIP.endswith('[') or UserLastIP.endswith('\r') or UserLastIP.endswith('\n') or UserLastIP.endswith('\x1B'):
            UserLastIP = UserLastIP[:len(UserLastIP) - 1]
        
        self.__ReceiveData[ConnectIndex] = self.__ReceiveData[ConnectIndex][self.__ReceiveData[ConnectIndex].find('《 五子棋 》'):]
        
        UserFiveChess = self.__ReceiveData[ConnectIndex][self.__ReceiveData[ConnectIndex].find('《 五子棋 》') + len('《 五子棋 》'):self.__ReceiveData[ConnectIndex].find('《象棋戰績》')]
        
        while UserFiveChess.endswith('m') or UserFiveChess.endswith(' ') or UserFiveChess.endswith('[') or UserFiveChess.endswith('\r') or UserFiveChess.endswith('\n') or UserFiveChess.endswith('\x1B'):
            UserFiveChess = UserFiveChess[:len(UserFiveChess) - 1]
        
        while UserFiveChess.find('  ') != -1:
            UserFiveChess = UserFiveChess.replace('  ', ' ')
        
        self.__ReceiveData[ConnectIndex] = self.__ReceiveData[ConnectIndex][self.__ReceiveData[ConnectIndex].find('《象棋戰績》'):]
        
        UserChess = self.__ReceiveData[ConnectIndex][self.__ReceiveData[ConnectIndex].find('《象棋戰績》') + len('《象棋戰績》'):self.__ReceiveData[ConnectIndex].find('和') + 1]
        
        while UserChess.endswith('m') or UserChess.endswith(' ') or UserChess.endswith('[') or UserChess.endswith('\r') or UserChess.endswith('\n') or UserChess.endswith('\x1B'):
            UserChess = UserChess[:len(UserChess) - 1]
        
        while UserChess.find('  ') != -1:
            UserChess = UserChess.replace('  ', ' ')
        
        self.__ReceiveData[ConnectIndex] = self.__ReceiveData[ConnectIndex][self.__ReceiveData[ConnectIndex].find('和') + 1:]
        
        result = UserInformation(UserID, UserMoney, UserLoginTime, UserPost, UserState, UserMail, UserLastLogin, UserLastIP, UserFiveChess, UserChess)
        
        return ErrorCode.Success, result
        
    def readPostFile(self, FileName):
        
        return Util.readPostFile(FileName)
    def getVersion(self):
        return Version
    
    def replyPost(self, Board, Content, ReplyType, PostID='', Index=-1, ConnectIndex = 0):

        if PostID == '' and Index == -1:
            self.Log('輸入參數錯誤')
            return self.ErrorInput
        
        if PostID != '':
            #def __gotoPostByID(self, Board, PostID, ConnectIndex = 0):
            ErrCode = self.__gotoPostByID(Board, PostID, ConnectIndex)
            if ErrCode != ErrorCode.Success:
                self.Log('replyPost 1 移動至文章失敗', LogLevel.DEBUG)
                return ErrorCode
        elif Index != -1:
            #def __gotoPostByIndex(self, Board, PostIndex, ConnectIndex=0):
            ErrCode = self.__gotoPostByIndex(Board, Index, ConnectIndex)
            if ErrCode != ErrorCode.Success:
                self.Log('replyPost 2 移動至文章失敗', LogLevel.DEBUG)
                return ErrorCode
                
        CaseList = [
        '二者皆是', 
        '很抱歉',
        '採用原標題', 
        '請問要引用原文嗎', 
        '編輯文章', 
        '確定要儲存檔案嗎',
        'x=隨機', 
        '請按任意鍵繼續', 
        '看板《' + Board + '》',
        '已順利寄出，是否自存底稿'
        ]
        SendMessage = 'rr'
        Enter = False
        self.__CurrentTimeout[ConnectIndex] = 10
        
        while True:
            ErrCode, Index = self.__sendData(ConnectIndex, SendMessage, CaseList, Enter)
            if ErrCode == self.WaitTimeout:
                self.__showScreen()
                self.Log('無法回文', LogLevel.DEBUG)
                return self.WaitTimeout
            if ErrCode != ErrorCode.Success:
                self.Log('replyPost 2 error code: ' + str(ErrorCode), LogLevel.DEBUG)
                return ErrorCode
            if Index == 0:
                if ReplyType == self.ReplyPost_Board:
                    SendMessage = 'F'
                    self.Log('replyPost 回應至 (F)看板', LogLevel.DEBUG)
                elif ReplyType == self.ReplyPost_Mail:
                    SendMessage = 'M'
                    self.Log('replyPost 回應至 (M)作者信箱', LogLevel.DEBUG)
                elif ReplyType == (self.ReplyPost_Board + self.ReplyPost_Mail):
                    SendMessage = 'B'
                    self.Log('replyPost 回應至 (B)二者皆是', LogLevel.DEBUG)
                else:
                    self.Log('replyPost 不支援的回文選項: ' + str(ReplyType), LogLevel.DEBUG)
                self.__CurrentTimeout[ConnectIndex] = 10
                Enter = True
            if Index == 1:
                SendMessage = 'Y'
                Enter = True
                self.__CurrentTimeout[ConnectIndex] = 10
                self.Log('replyPost 回信給作者', LogLevel.DEBUG)
            if Index == 2:
                SendMessage = 'Y'
                Enter = True
                self.Log('replyPost 採用原標題', LogLevel.DEBUG)
            if Index == 3:
                SendMessage = 'Y'
                Enter = True
                self.Log('replyPost 引用原文', LogLevel.DEBUG)
            if Index == 4:
                SendMessage = Content + '\r\x18'
                Enter = True
                self.__CurrentTimeout[ConnectIndex] = 10
                self.Log('replyPost 編輯文章', LogLevel.DEBUG)
            if Index == 5:
                SendMessage = 's'
                Enter = True
                self.Log('replyPost 儲存檔案', LogLevel.DEBUG)
            if Index == 6:
                SendMessage = str(0)
                Enter = True
            if Index == 7:
                SendMessage = 'q'
                Enter = False
            if Index == 8:
                #self.Log('Post Success')
                break
            if Index == 9:
                SendMessage = 'Y'
                Enter = True
                self.Log('replyPost 已順利寄出', LogLevel.DEBUG)
        
        return ErrorCode.Success
    def getMail(self, inputMailIndex, ConnectIndex = 0):
        try:
            MailIndex = int(inputMailIndex)
        except ValueError:
            self.Log('錯誤的信件編號: ' + str(inputMailIndex), LogLevel.INFO)
            return self.ErrorInput, None

        if MailIndex < 1:
            self.Log('過小的信件編號: ' + str(MailIndex), LogLevel.INFO)
            return self.ErrorInput, None

        ErrCode = self.__gotoTop(ConnectIndex)
        if ErrCode != ErrorCode.Success:
            print('無法移動至主選單: ' + str(ErrorCode))
            return ErrCode, None
        
        ErrCode, NewestMailIndex = self.getNewestMailIndex(ConnectIndex)
        if ErrCode != ErrorCode.Success:
            print('無法移動至主選單: ' + str(ErrorCode))
            return ErrCode, None

        if NewestMailIndex == 0:
            self.Log('信箱中沒有郵件')
            return ErrorCode.Success, None
        else:
            self.Log('信箱中最新郵件編號: ' + str(NewestMailIndex), LogLevel.DEBUG)

        if inputMailIndex > NewestMailIndex:
            self.Log('錯誤的輸入!輸入的郵件編號(' + str(inputMailIndex) + ')超過目前的郵件編號(' + str(NewestMailIndex) + ')')
            return self.ErrorInput, None
        
        self.__CurrentTimeout[ConnectIndex] = 2
        self.__readScreen(ConnectIndex, str(inputMailIndex) + '\r\r', ['瀏覽'])

        # print(self.__ReceiveData[ConnectIndex])
        
        MailAuthor = self.__ReceiveData[ConnectIndex]
        MailAuthor = MailAuthor[MailAuthor.find('作者 [0;44m ') + len('作者 [0;44m '):]
        MailAuthor = MailAuthor[:MailAuthor.find('\r')]
        while MailAuthor.endswith(' '):
            MailAuthor = MailAuthor[:-1]

        MailTitle = self.__ReceiveData[ConnectIndex]
        MailTitle = MailTitle[MailTitle.find('標題 [0;44m ') + len('標題 [0;44m '):]
        MailTitle = MailTitle[:MailTitle.find('\r')]
        while MailTitle.endswith(' '):
            MailTitle = MailTitle[:-1]
        
        MailDate = self.__ReceiveData[ConnectIndex]
        MailDate = MailDate[MailDate.find('時間 [0;44m ') + len('時間 [0;44m '):]
        MailDate = MailDate[:MailDate.find('\r')]
        while MailDate.endswith(' '):
            MailDate = MailDate[:-1]

        MailContentTemp = []
        MailContentTemp.append(self.__ReceiveData[ConnectIndex])
        MailContentTemp[0] = MailContentTemp[0][MailContentTemp[0].find('[36m───────────────────────────────────────[37m ') + len('[36m───────────────────────────────────────[37m '):]
        MailContentTemp[0] = MailContentTemp[0][MailContentTemp[0].find('[m') + len('[m'):]

        MailContentTemp[0] = MailContentTemp[0][:MailContentTemp[0].find('瀏覽 第') - 11]

        LastLineCount = [1, 22]
        MailPage = 2
        while '頁 (100%)' not in self.__ReceiveData[ConnectIndex]:
            
            self.__CurrentTimeout[ConnectIndex] = 2
            self.__readScreen(ConnectIndex, str(MailPage) + '\r', ['瀏覽'])
            MailPage += 1

            MailContentTempTemp = self.__ReceiveData[ConnectIndex]
            MailContentTempTemp = MailContentTempTemp[len('[H [2J'):]
            MailContentTempTemp = MailContentTempTemp[:MailContentTempTemp.find('瀏覽 第') - 11]

            LineCountTemp = self.__ReceiveData[ConnectIndex]
            LineCountTemp = LineCountTemp[LineCountTemp.find('目前顯示: 第 ') + len('目前顯示: 第 '):]
            LineCountTemp = LineCountTemp[:LineCountTemp.find(' 行')]
            LastLineCountTemp = list(map(int, re.findall(r'\d+', LineCountTemp)))

            # print(LastLineCount)
            # print(LastLineCountTemp)
            if LastLineCountTemp[0] != LastLineCount[1] + 1:
                SubLine = (LastLineCount[1] + 1) - LastLineCountTemp[0]
                # print('重疊: ' + str(SubLine) + ' 行')

                for i in range(SubLine):
                    MailContentTempTemp = MailContentTempTemp[MailContentTempTemp.find('\r') + 2:]
            
            MailContentTemp.append(MailContentTempTemp)
            LastLineCount = LastLineCountTemp
        MailContent = ''.join(MailContentTemp)
        
        MailIP = MailContent[MailContent.find('ptt.cc), 來自: ') + len('ptt.cc), 來自: '):]
        MailIP = MailIP[:MailIP.find('[')]
        MailIP = MailIP[:MailIP.find('\r')]
        MailIP = MailIP.replace(' ', '')

        MailContent = MailContent[:MailContent.find('※ 發信站: 批踢踢實業坊(ptt.cc), 來自:') - 5]
        
        result = MailInformation(MailAuthor, MailTitle, MailDate, MailContent, MailIP)

        return ErrorCode.Success, result
    def getNewestMailIndex(self, ConnectIndex = 0):

        ErrCode = self.__gotoTop(ConnectIndex)
        if ErrCode != ErrorCode.Success:
            print('無法移動至主選單: ' + str(ErrorCode))
            return ErrCode, None
        # self.__showScreen()

        CaseList = [
            '我的信箱', 
            '鴻雁往返'
        ]
        SendMessage = 'm'
        Enter = True
        self.__CurrentTimeout[ConnectIndex] = 10
        
        while True:
            ErrCode, Index = self.__sendData(ConnectIndex, SendMessage, CaseList, Enter)
            if ErrCode == self.WaitTimeout:
                self.__showScreen()
                self.Log('無法前進至信箱', LogLevel.DEBUG)
                return self.WaitTimeout, None
            if ErrCode != ErrorCode.Success:
                self.Log('getMail 錯誤: ' + str(ErrorCode), LogLevel.DEBUG)
                return ErrCode, None
            if Index == 0:
                self.__CurrentTimeout[ConnectIndex] = 10
                SendMessage = 'r'
                Enter = True
                self.Log('進入私人信件區', LogLevel.DEBUG)
            elif Index == 1:
                self.Log('進入郵件選單', LogLevel.DEBUG)
                break
            else:
                self.Log('else', LogLevel.DEBUG)
                self.__showScreen()
                return self.UnknowError, None
        
        self.__CurrentTimeout[ConnectIndex] = 2
        self.__readScreen(ConnectIndex, '0\r$', ['鴻雁往返'])

        MaxMail = 0
        for i in reversed(range(1000)):
            if '/' + str(i) + '篇' in self.__ReceiveData[ConnectIndex]:
                MaxMail = i
                break
        if MaxMail == 0:
            self.Log('取得信箱最高容量失敗')
            return self.UnknowError, None
        self.Log('此信箱最高容量: '+ str(MaxMail), LogLevel.DEBUG)

        if self.__Cursor == '>':
            MailIndexTest = 5
        elif self.__Cursor == '●':
            MailIndexTest = 4
        else:
            self.Log('無游標')
            return self.UnknowError, None
        NewestMailIndex = 0
        for i in reversed(range(MaxMail + 1)):
            TestString = self.__Cursor + (' ' * (MailIndexTest - len(str(i)))) + str(i)
            if TestString in self.__ReceiveData[ConnectIndex]:
                NewestMailIndex = i
                break
        if NewestMailIndex == 0:
            self.Log('信箱中沒有郵件')
            return ErrorCode.Success, None
        else:
            self.Log('信箱中最新郵件編號: ' + str(NewestMailIndex), LogLevel.DEBUG)
        
        return ErrorCode.Success, NewestMailIndex

if __name__ == '__main__':

    print('PTT Library v ' + Version)
    print('Developed by PTT CodingMan')