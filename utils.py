import os
import sys
import atexit
import socket
import subprocess
import logging
import threading
from typing import List ,Dict ,Any

from PyQt6 .QtCore import QObject ,QEvent ,QPropertyAnimation ,QEasingCurve ,QParallelAnimationGroup ,QPointF ,Qt ,QVariantAnimation ,QPoint ,QTimer 
from PyQt6 .QtGui import QColor 
from PyQt6 .QtWidgets import QMessageBox ,QWidget ,QPushButton ,QToolButton ,QLineEdit ,QComboBox ,QGraphicsDropShadowEffect ,QGraphicsOpacityEffect ,QMenu ,QFrame ,QApplication 

from config import SETTINGS ,save_settings 
from core .env_manager import EnvManager 
from core .window_effect import WindowEffect 

logger =logging .getLogger (__name__ )

ENV_WARNED ={}
JAVA_WARNED =False 


class _LiquidGlassAnimFilter (QObject ):

    def __init__ (self ,parent =None ):
        super ().__init__ (parent )

    def _ensure_effect (self ,w :QWidget )->QGraphicsDropShadowEffect :

        eff =w .graphicsEffect ()
        if isinstance (eff ,QGraphicsDropShadowEffect ):
            return eff 

        eff =QGraphicsDropShadowEffect (w )
        eff .setBlurRadius (0 )
        eff .setOffset (0 ,0 )
        eff .setColor (QColor (0 ,0 ,0 ,0 ))
        w .setGraphicsEffect (eff )
        return eff 

    def _start_pulse (self ,w :QWidget ,base_color :QColor ):

        anim =getattr (w ,"_lg_pulse",None )
        if isinstance (anim ,QVariantAnimation ):
            if anim .state ()==QVariantAnimation .State .Running :
                return 
        else :
            anim =QVariantAnimation (w )
            anim .setLoopCount (-1 )
            anim .setDuration (1400 )
            anim .setEasingCurve (QEasingCurve .Type .InOutSine )
            w ._lg_pulse =anim 

        eff =self ._ensure_effect (w )


        if not getattr (w ,"_lg_pulse_connected",False ):
            def _on_val (v ):

                t =float (v )

                a =int (55 +(110 -55 )*t )
                c =QColor (base_color )
                c .setAlpha (a )
                eff .setColor (c )

            anim .valueChanged .connect (_on_val )
            w ._lg_pulse_connected =True 


        anim .setStartValue (0.0 )
        anim .setKeyValueAt (0.5 ,1.0 )
        anim .setEndValue (0.0 )
        anim .start ()

    def _stop_pulse (self ,w :QWidget ):
        anim =getattr (w ,"_lg_pulse",None )
        if isinstance (anim ,QVariantAnimation )and anim .state ()==QVariantAnimation .State .Running :
            anim .stop ()

    def _apply_state (self ,w :QWidget ,state :str ):
        eff =self ._ensure_effect (w )

        if getattr (w ,"_lg_anim_group",None )is None :
            group =QParallelAnimationGroup (w )

            anim_blur =QPropertyAnimation (eff ,b"blurRadius",group )
            anim_blur .setDuration (220 )
            anim_blur .setEasingCurve (QEasingCurve .Type .OutBack )

            anim_off =QPropertyAnimation (eff ,b"offset",group )
            anim_off .setDuration (220 )
            anim_off .setEasingCurve (QEasingCurve .Type .OutBack )

            anim_col =QPropertyAnimation (eff ,b"color",group )
            anim_col .setDuration (220 )
            anim_col .setEasingCurve (QEasingCurve .Type .OutBack )

            w ._lg_anim_group =group 
            w ._lg_anim_blur =anim_blur 
            w ._lg_anim_off =anim_off 
            w ._lg_anim_col =anim_col 

        group :QParallelAnimationGroup =w ._lg_anim_group 
        if group .state ()==QParallelAnimationGroup .State .Running :
            group .stop ()

        base_glow =QColor (0 ,122 ,255 ,1 )

        blur =0.0 
        off =QPointF (0.0 ,0.0 )
        col =QColor (0 ,0 ,0 ,0 )


        dur =220 
        easing =QEasingCurve .Type .OutBack 

        if state =="hover":
            blur =26.0 
            off =QPointF (0.0 ,10.0 )
            col =QColor (base_glow )
            col .setAlpha (85 )
            self ._start_pulse (w ,base_glow )
        elif state =="focus":
            blur =30.0 
            off =QPointF (0.0 ,12.0 )
            col =QColor (base_glow )
            col .setAlpha (105 )
            self ._start_pulse (w ,base_glow )
        elif state =="press":
            blur =18.0 
            off =QPointF (0.0 ,4.0 )
            col =QColor (base_glow )
            col .setAlpha (95 )
            dur =110 
            easing =QEasingCurve .Type .OutCubic 
            self ._stop_pulse (w )
        elif state =="idle":
            blur =0.0 
            off =QPointF (0.0 ,0.0 )
            col =QColor (0 ,0 ,0 ,0 )
            self ._stop_pulse (w )

        w ._lg_anim_blur .setDuration (dur )
        w ._lg_anim_off .setDuration (dur )
        w ._lg_anim_col .setDuration (dur )
        w ._lg_anim_blur .setEasingCurve (easing )
        w ._lg_anim_off .setEasingCurve (easing )
        w ._lg_anim_col .setEasingCurve (easing )

        w ._lg_anim_blur .setStartValue (eff .blurRadius ())

        w ._lg_anim_blur .setKeyValueAt (0.0 ,eff .blurRadius ())
        w ._lg_anim_blur .setKeyValueAt (0.70 ,blur +(3.0 if state in ("hover","focus")else 0.0 ))
        w ._lg_anim_blur .setKeyValueAt (1.0 ,blur )
        w ._lg_anim_off .setStartValue (eff .offset ())
        w ._lg_anim_off .setEndValue (off )
        w ._lg_anim_col .setStartValue (eff .color ())
        w ._lg_anim_col .setEndValue (col )
        group .start ()

    def eventFilter (self ,obj ,event ):
        if not isinstance (obj ,QWidget ):
            return False 

        et =event .type ()
        if et ==QEvent .Type .Enter :
            if obj .hasFocus ():
                self ._apply_state (obj ,"focus")
            else :
                self ._apply_state (obj ,"hover")
        elif et ==QEvent .Type .Leave :
            if obj .hasFocus ():
                self ._apply_state (obj ,"focus")
            else :
                self ._apply_state (obj ,"idle")
        elif et ==QEvent .Type .FocusIn :
            self ._apply_state (obj ,"focus")
        elif et ==QEvent .Type .FocusOut :
            if obj .underMouse ():
                self ._apply_state (obj ,"hover")
            else :
                self ._apply_state (obj ,"idle")
        elif et ==QEvent .Type .MouseButtonPress :
            self ._apply_state (obj ,"press")
        elif et ==QEvent .Type .MouseButtonRelease :
            if obj .hasFocus ():
                self ._apply_state (obj ,"focus")
            elif obj .underMouse ():
                self ._apply_state (obj ,"hover")
            else :
                self ._apply_state (obj ,"idle")

        return False 


class _PopupBlurFilter (QObject ):
    def __init__ (self ,parent =None ):
        super ().__init__ (parent )
        self ._effect =WindowEffect ()

    def _apply (self ,w :QWidget ):
        if w is None :
            return 
        if sys .platform !="win32":
            return 
        try :
            hwnd =int (w .winId ())
        except Exception :
            return 

        try :
            self ._effect .set_acrylic_effect (hwnd ,is_dark =True )
        except Exception :
            return 

    def eventFilter (self ,obj ,event ):
        if SETTINGS .get ("theme")!="red_blue_glass":
            return False 

        if not isinstance (obj ,QWidget ):
            return False 

        et =event .type ()
        if et !=QEvent .Type .Show :
            return False 

        try :
            if isinstance (obj ,QMenu ):
                QTimer .singleShot (0 ,lambda w =obj :self ._apply (w ))
                return False 

            if isinstance (obj ,QFrame )and obj .objectName ()=="qt_combobox_popup":
                QTimer .singleShot (0 ,lambda w =obj :self ._apply (w ))
                return False 
        except Exception :
            return False 

        return False 


def install_liquid_glass_animations (root :QWidget ):
    if root is None :
        return 

    if SETTINGS .get ("theme")!="liquid_glass":
        return 

    f =getattr (root ,"_lg_anim_filter",None )
    if f is None :
        f =_LiquidGlassAnimFilter (root )
        root ._lg_anim_filter =f 

    classes =(QPushButton ,QToolButton ,QLineEdit ,QComboBox )
    widgets =[root ]+root .findChildren (QWidget )
    for w in widgets :
        if not isinstance (w ,classes ):
            continue 
        if getattr (w ,"_lg_anim_installed",False ):
            continue 
        w ._lg_anim_installed =True 
        w .setAttribute (Qt .WidgetAttribute .WA_Hover ,True )
        w .setMouseTracking (True )
        w .installEventFilter (f )


def install_red_blue_glass_popup_blur (root :QWidget ):
    if root is None :
        return 
    if SETTINGS .get ("theme")!="red_blue_glass":
        return 

    app =QApplication .instance ()
    if app is None :
        return 

    f =getattr (app ,"_rbg_popup_blur_filter",None )
    if f is None :
        f =_PopupBlurFilter (app )
        app ._rbg_popup_blur_filter =f 
        app .installEventFilter (f )


def animate_liquid_glass_fade (widget :QWidget ,*,start_opacity :float =0.78 ,duration_ms :int =240 ):
    if widget is None :
        return 
    if SETTINGS .get ("theme")!="liquid_glass":
        return 

    eff =widget .graphicsEffect ()
    if not isinstance (eff ,QGraphicsOpacityEffect ):
        eff =QGraphicsOpacityEffect (widget )
        eff .setOpacity (1.0 )
        widget .setGraphicsEffect (eff )

    anim =getattr (widget ,"_lg_fade_anim",None )
    if isinstance (anim ,QPropertyAnimation ):
        try :
            anim .stop ()
        except Exception :
            pass 
    anim =QPropertyAnimation (eff ,b"opacity",widget )
    anim .setDuration (duration_ms )
    anim .setEasingCurve (QEasingCurve .Type .OutCubic )
    anim .setStartValue (start_opacity )
    anim .setEndValue (1.0 )
    widget ._lg_fade_anim =anim 
    anim .start ()


def animate_liquid_glass_menu (menu :QMenu ,*,start_pos :QPoint ,end_pos :QPoint ):
    if menu is None :
        return 
    if SETTINGS .get ("theme")!="liquid_glass":
        return 

    try :
        menu .setWindowOpacity (0.0 )
    except Exception :
        return 


    fade =QPropertyAnimation (menu ,b"windowOpacity",menu )
    fade .setDuration (180 )
    fade .setEasingCurve (QEasingCurve .Type .OutCubic )
    fade .setStartValue (0.0 )
    fade .setEndValue (1.0 )


    move =QPropertyAnimation (menu ,b"pos",menu )
    move .setDuration (220 )
    move .setEasingCurve (QEasingCurve .Type .OutBack )
    move .setStartValue (start_pos )
    move .setEndValue (end_pos )

    group =QParallelAnimationGroup (menu )
    group .addAnimation (fade )
    group .addAnimation (move )
    menu ._lg_menu_anim =group 
    group .start ()



_instance_socket =None
_instance_lock_file =None
_LOCK_MAGIC =b"TH3_PING\x00"
_LOCK_RESPONSE =b"TH3_PONG\x00"


def _cleanup_lock ():

    global _instance_lock_file
    try :
        if _instance_lock_file :
            _instance_lock_file .close ()
        lock_path =os .path .join (os .path .dirname (os .path .abspath (__file__)),"config",".instance.lock")
        if os .path .exists (lock_path ):
            os .remove (lock_path )
    except :
        pass


def _probe_existing (port :int )->bool :

    try :
        s =socket .socket (socket .AF_INET ,socket .SOCK_STREAM )
        s .settimeout (1.0 )
        s .connect (("127.0.0.1",port ))
        s .sendall (_LOCK_MAGIC )
        resp =s .recv (len (_LOCK_RESPONSE ))
        s .close ()
        return resp ==_LOCK_RESPONSE
    except :
        return False


def _lock_listener (sock :socket .socket ):

    sock .listen (5 )
    while True :
        try :
            conn ,_ =sock .accept ()
            conn .settimeout (2.0 )
            data =conn .recv (1024 )
            if data .startswith (_LOCK_MAGIC ):
                conn .sendall (_LOCK_RESPONSE )
            conn .close ()
        except (OSError ,socket .timeout ):
            continue


def ensure_single_instance ()->bool :
    global _instance_socket ,_instance_lock_file

    app_dir =os .path .dirname (os .path .abspath (__file__))
    lock_path =os .path .join (app_dir ,"config",".instance.lock")


    if os .path .exists (lock_path ):
        try :
            with open (lock_path ,'r')as f :
                port =int (f .read ().strip ())
            if _probe_existing (port ):
                msg =QMessageBox ()
                msg .setWindowTitle ("提示")
                msg .setIcon (QMessageBox .Icon .Warning )
                msg .setText ("程序已经在运行中！\n不会再次启动新的工具箱进程了")
                msg .exec ()
                return False
            else :
                try :
                    os .remove (lock_path )
                except :
                    pass
        except (ValueError ,OSError ):
            try :
                os .remove (lock_path )
            except :
                pass


    try :
        s =socket .socket (socket .AF_INET ,socket .SOCK_STREAM )
        s .bind (("127.0.0.1",0 ))
        port =s .getsockname ()[1 ]
    except OSError as e :
        msg =QMessageBox ()
        msg .setWindowTitle ("提示")
        msg .setIcon (QMessageBox .Icon .Warning )
        msg .setText (f"无法绑定网络端口：{e }")
        msg .exec ()
        return False


    s .settimeout (5.0 )
    listener =threading .Thread (target =_lock_listener ,args =(s ,),daemon =True )
    listener .start ()

    _instance_socket =s


    try :
        os .makedirs (os .path .dirname (lock_path ),exist_ok =True )
        _instance_lock_file =open (lock_path ,'w')
        _instance_lock_file .write (str (port ))
        _instance_lock_file .flush ()
    except OSError :
        pass


    atexit .register (_cleanup_lock )

    return True 

def find_cli_interpreter (name :str ,typ :str ):
    try :
        env_mgr =EnvManager ()
        item =env_mgr ._find_cli_interpreter (typ ,name )
        return item 
    except Exception :
        return None 

def _safe_quote (s :str )->str :
    if not s :
        return '""'
    s =str (s )
    if '"' in s or ' ' in s or '&' in s or '|' in s or ';' in s or '(' in s or ')' in s or '^' in s or '%' in s :
        return '"' +s .replace ('"','""')+'"'
    return s

def _safe_basename (p :str )->str :
    return os .path .basename (str (p ).replace ('/','\\').rstrip ('\\'))

def run_tool (tool_data :Dict [str ,Any ],record_recent =True )->bool :
    tool_type =tool_data .get ("type","")
    path =tool_data .get ("path","")
    params =tool_data .get ("params","")
    url =tool_data .get ("url","")

    base_path =os .path .abspath ("tools")
    if os .path .isabs (path ):
        abs_path =path
    else :
        abs_path =os .path .join (base_path ,path)

    env_mgr =EnvManager ()

    try :
        if tool_type =="网页":
            import webbrowser
            if url :
                if not url .lower ().startswith (("http://","https://")):
                    url ="http://"+url
                webbrowser .open (url)
            else :
                raise RuntimeError ("无效的网页地址")

        elif tool_type .startswith ("Python("):
            name =tool_data .get ("custom_interpreter_name","")
            ci =find_cli_interpreter (name ,"python")
            if not ci or not os .path .exists (str (ci .get ("path",""))):
                raise RuntimeError (f"未找到自定义Python解释器[{name}]的路径")
            pyexe =str (ci .get ("path",""))
            env =env_mgr .get_injected_env (tool_type)
            cmd =f'cmd /c start cmd /k "cd /d \"{os.path.dirname(abs_path)}\" && \"{pyexe}\" \"{os.path.basename(abs_path)}\" {params}"'
            subprocess .Popen (cmd ,shell =True ,env =env)

        elif tool_type .startswith ("Java("):
            name =tool_data .get ("custom_interpreter_name","")
            ci =find_cli_interpreter (name ,"java")
            if not ci or not os .path .exists (str (ci .get ("path",""))):
                raise RuntimeError (f"未找到自定义Java路径[{name}]")
            java_dir =str (ci .get ("path",""))
            java_exe =os .path .join (java_dir ,"java.exe")
            env =env_mgr .get_injected_env (tool_type)
            cmd =f"\"{java_exe}\" -jar \"{abs_path}\" {params}"
            subprocess .Popen (cmd ,shell =True ,cwd =os .path .dirname (abs_path),env =env)

        else :
            if tool_type .startswith ("JAVA"):
                version ="8"if "8"in tool_type else "11"
                is_gui ="图形化"in tool_type
                java_exe =env_mgr .get_java_exe (version ,gui =is_gui)
                env =env_mgr .get_injected_env (f"java{version}")
                cmd =f"\"{java_exe}\" -jar \"{abs_path}\" {params}"
                subprocess .Popen (cmd ,shell =True ,cwd =os .path .dirname (abs_path),env =env)

            elif tool_type =="Python":
                pyexe =env_mgr .get_python_path ()
                env =env_mgr .get_injected_env ("python")
                cmd =f'cmd /c start cmd /k "cd /d \"{os.path.dirname(abs_path)}\" && \"{pyexe}\" \"{os.path.basename(abs_path)}\" {params}"'
                subprocess .Popen (cmd ,shell =True ,env =env)

            elif tool_type =="GUI应用":
                env =env_mgr .get_injected_env ("all")
                cmd =f"cmd /c start \"\" \"{abs_path}\" {params}"
                subprocess .Popen (cmd ,shell =True ,cwd =os .path .dirname (abs_path),env =env)

            elif tool_type =="命令行":
                env =env_mgr .get_injected_env ("all")
                cmd =f"cmd /c start cmd /k \"cd /d \"{os.path.dirname(abs_path)}\" && \"{os.path.basename(abs_path)}\" {params}\""
                subprocess .Popen (cmd ,shell =True ,env =env)

            elif tool_type =="批处理":
                env =env_mgr .get_injected_env ("all")
                ext =os .path .splitext (abs_path)[1 ].lower ()
                if ext ==".vbs":
                    cmd =f"cmd /c start cmd /k \"cd /d \"{os.path.dirname(abs_path)}\" && wscript \"{os.path.basename(abs_path)}\" {params}\""
                else :
                    cmd =f"cmd /c start cmd /k \"cd /d \"{os.path.dirname(abs_path)}\" && \"{os.path.basename(abs_path)}\" {params}\""
                subprocess .Popen (cmd ,shell =True ,env =env)

            elif tool_type =="PowerShell":
                env =env_mgr .get_injected_env ("all")
                cmd =f"cmd /c start powershell -noexit -command \"cd '{os.path.dirname(abs_path)}'; .\\{os.path.basename(abs_path)} {params}\""
                subprocess .Popen (cmd ,shell =True ,env =env)

            else :
                raise RuntimeError ("不支持的工具类型")

        if record_recent :
            try :
                add_recent_tool (tool_data)
            except Exception as e :
                logger .warning (f"记录最近启动历史失败: {e}")

        logger .info (f"[运行工具] {cmd}")

        return True

    except Exception as e :
        logger .error (f"run_tool失败: {e}")
        QMessageBox .warning (None ,"错误",f"执行工具时出现异常: {e}")
        return False

def run_tools_batch (tools :List [Dict [str ,Any ]])->int :
    cnt =0 
    for t in tools :
        if run_tool (t ,record_recent =True ):
            cnt +=1 
    return cnt 

def check_environment (env_type :str )->bool :
    env_mgr =EnvManager ()
    try :
        if env_type =="网页":
            return True 
        if env_type .startswith ("Python("):
            return True 
        if env_type .startswith ("Java("):
            return True 

        if env_type .startswith ("JAVA"):
            version ="8"if "8"in env_type else "11"
            home =env_mgr .get_java_home (version )
            if not home :
                if not ENV_WARNED .get (f"JAVA{version}",False ):
                    ENV_WARNED [f"JAVA{version}"]=True 
                    QMessageBox .warning (None ,"错误",f"未检测到 JAVA{version} 运行环境 (程序包或系统)")
                return False 
            return True 

        elif env_type =="Python":
            py =env_mgr .get_python_path ()
            if py and (os .path .exists (py )or py =="python"):
                return True 
            if not ENV_WARNED .get ("PYTHON",False ):
                ENV_WARNED ["PYTHON"]=True 
                QMessageBox .warning (None ,"错误","未检测到有效的 Python 运行环境")
            return False 

        elif env_type in ["命令行","GUI应用","批处理","PowerShell"]:
            return True 

        return True 

    except :
        return True 

def validate_java_path ():
    check_environment ("JAVA8")
    check_environment ("JAVA11")
    return True 

def fuzzy_search (tools :List [Dict [str ,Any ]],search_text :str )->List [Dict [str ,Any ]]:
    if not search_text :
        return tools 
    try :
        st =str (search_text ).casefold ()
    except Exception :
        st =""
    ret =[]
    for t in tools :
        try :
            nm =str (t .get ('name','')).casefold ()
            desc =str (t .get ("description","")).casefold ()
            cat =str (t .get ('category','')).casefold ()
            tags_val =t .get ("tags",[])
            if isinstance (tags_val ,(list ,tuple ,set )):
                tags =" ".join ([str (x )for x in tags_val ]).casefold ()
            else :
                tags =str (tags_val ).casefold ()
        except Exception :
            nm =""
            desc =""
            cat =""
            tags =""
        if (st in nm )or (st in desc )or (st in cat )or (st in tags ):
            ret .append (t )
    return ret 

def is_tool_favorited (tool :Dict [str ,Any ])->bool :
    favs =SETTINGS .get ("favorite_tools",[])
    key =(tool ['name'],tool ['category'])
    return list (key )in favs or key in favs 

def add_favorite_tool (tool :Dict [str ,Any ])->bool :
    favs =SETTINGS .get ("favorite_tools",[])
    key =[tool ['name'],tool ['category']]
    if key not in favs :
        favs .append (key )
        SETTINGS ["favorite_tools"]=favs 
        save_settings (SETTINGS )
        return True 
    return False 

def remove_favorite_tool (tool :Dict [str ,Any ])->bool :
    favs =SETTINGS .get ("favorite_tools",[])
    key =[tool ['name'],tool ['category']]
    if key in favs :
        favs .remove (key )
        SETTINGS ["favorite_tools"]=favs 
        save_settings (SETTINGS )
        return True 
    return False 

def get_favorite_tools (all_tools :List [Dict [str ,Any ]])->List [Dict [str ,Any ]]:
    favs =SETTINGS .get ("favorite_tools",[])
    result =[]
    for t in all_tools :
        key =[t ['name'],t ['category']]
        if key in favs :
            result .append (t )
    return result 

def add_recent_tool (tool :Dict [str ,Any ],max_count =10 ):
    recents =SETTINGS .get ("recent_tools",[])
    key =[tool ['name'],tool ['category']]
    recents =[v for v in recents if v !=key ]
    recents .insert (0 ,key )
    if len (recents )>max_count :
        recents =recents [:max_count ]
    SETTINGS ["recent_tools"]=recents 
    save_settings (SETTINGS )

def get_recent_tools (all_tools :List [Dict [str ,Any ]])->List [Dict [str ,Any ]]:
    recents =SETTINGS .get ("recent_tools",[])
    result =[]
    for key in recents :
        for t in all_tools :
            if t ['name']==key [0 ]and t ['category']==key [1 ]:
                result .append (t )
                break 
    return result 

def save_main_window_geometry (geometry_bytes ):
    import base64 
    SETTINGS ["main_window_geometry"]=base64 .b64encode (geometry_bytes ).decode ("ascii")
    save_settings (SETTINGS )

def load_main_window_geometry ():
    import base64 
    geom =SETTINGS .get ("main_window_geometry",None )
    if geom :
        try :
            return base64 .b64decode (geom )
        except Exception :
            return None 
    return None 

def save_main_window_state (state_bytes ):
    import base64 
    SETTINGS ["main_window_state"]=base64 .b64encode (state_bytes ).decode ("ascii")
    save_settings (SETTINGS )

def load_main_window_state ():
    import base64 
    st =SETTINGS .get ("main_window_state",None )
    if st :
        try :
            return base64 .b64decode (st )
        except Exception :
            return None 
    return None 

from PyQt6 .QtCore import QObject ,pyqtSignal ,QThread 

class SearchWorker (QObject ):
    result_ready =pyqtSignal (list )
    searching =pyqtSignal ()
    def __init__ (self ,tools ,search_text ,filter_func =None ):
        super ().__init__ ()

        self .tools =tools 
        self .search_text =search_text 
        self .filter_func =filter_func 

    def run (self ):
        self .searching .emit ()
        if self .filter_func :
            filtered =self .filter_func (self .tools )
        else :
            filtered =fuzzy_search (self .tools ,self .search_text )
        self .result_ready .emit (filtered )
