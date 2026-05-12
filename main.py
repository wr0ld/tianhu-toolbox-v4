import sys
import os
import logging
import subprocess
# import keyboard  # 已禁用全局热键功能
import threading
import time
import traceback
import logging .handlers
from PyQt6 .QtWidgets import (
QApplication ,QMainWindow ,QMessageBox ,QWidget ,
QVBoxLayout ,QHBoxLayout ,QPushButton ,QSystemTrayIcon ,QMenu ,
QFileDialog ,QInputDialog ,QLabel ,QLineEdit ,QAbstractButton 
)
from PyQt6 .QtCore import Qt ,QSettings ,QByteArray ,QTimer ,pyqtSignal ,QThread ,QObject ,QEvent ,QVariantAnimation ,QEasingCurve ,qInstallMessageHandler ,QtMsgType 
from PyQt6 .QtGui import QPainter ,QPixmap ,QShortcut ,QKeySequence 
from PyQt6 .QtGui import QIcon 

from config import (
SETTINGS ,THEME ,load_settings ,save_settings ,load_theme ,
load_tools ,load_categories ,save_tools ,save_categories ,DEFAULT_CATEGORIES ,
export_all_data ,import_all_data
)
from utils import (
ensure_single_instance ,check_environment ,validate_java_path ,run_tool ,
run_tools_batch ,is_tool_favorited ,add_favorite_tool ,remove_favorite_tool ,
save_main_window_geometry ,load_main_window_geometry ,save_main_window_state ,load_main_window_state ,
SearchWorker ,fuzzy_search ,get_favorite_tools ,get_recent_tools
)
from widgets import (
TitleBar ,SearchBar ,CategoryPanel ,
ToolDialog ,SettingsDialog
)
from core .window_effect import WindowEffect
from core .modern_grid import ModernToolGrid
from services.tool_health import ToolHealthChecker
# from views.terminal_tab_widget import TerminalTabWidget  # 已禁用终端功能

class _RateLimitingHandler (logging .Handler ):
    def __init__ (self ,inner :logging .Handler ,*,window_sec :float =10.0 ,max_per_key :int =20 ):
        super ().__init__ (level =inner .level )
        self ._inner =inner 
        self ._window =float (window_sec )
        self ._max =int (max_per_key )
        self ._state ={}
        self ._lock =threading .Lock ()

    def setFormatter (self ,fmt ):
        try :
            self ._inner .setFormatter (fmt )
        except Exception :
            pass 
        return super ().setFormatter (fmt )

    def _make_key (self ,record :logging .LogRecord ):
        try :
            msg =record .getMessage ()
        except Exception :
            msg =""
        if len (msg )>220 :
            msg =msg [:220 ]
        return (record .levelno ,record .name ,msg )

    def _emit_summary (self ,key ,suppressed :int ):
        try :
            levelno ,name ,msg =key 
            summary =logging .LogRecord (
            name =name ,
            level =levelno ,
            pathname ="",
            lineno =0 ,
            msg =f"[log-suppress] suppressed {suppressed} similar logs in last {int (self ._window )}s: {msg}",
            args =(),
            exc_info =None ,
            func =None ,
            sinfo =None ,
            )
            self ._inner .emit (summary )
        except Exception :
            pass 

    def emit (self ,record :logging .LogRecord ):
        now =time .time ()
        key =self ._make_key (record )
        with self ._lock :
            st =self ._state .get (key )
            if st is None :
                st =[now ,0 ,0 ]
                self ._state [key ]=st 
            win_start ,count ,supp =st [0 ],st [1 ],st [2 ]

            if now -win_start >=self ._window :
                if supp >0 :
                    self ._emit_summary (key ,supp )
                win_start =now 
                count =0 
                supp =0 

            if count <self ._max :
                st [0 ],st [1 ],st [2 ]=win_start ,count +1 ,supp 
                try :
                    self ._inner .emit (record )
                except Exception :
                    pass 
            else :
                st [0 ],st [1 ],st [2 ]=win_start ,count ,supp +1 


_fmt =logging .Formatter ('%(asctime)s - %(levelname)s - %(message)s')
_file =logging .handlers .RotatingFileHandler (
"app.log",maxBytes =2 *1024 *1024 ,backupCount =5 ,encoding ="utf-8"
)
_file .setFormatter (_fmt )
_console =logging .StreamHandler ()
_console .setFormatter (_fmt )

_file_rl =_RateLimitingHandler (_file ,window_sec =10.0 ,max_per_key =30 )
_console_rl =_RateLimitingHandler (_console ,window_sec =10.0 ,max_per_key =30 )

root_logger =logging .getLogger ()
root_logger .setLevel (logging .INFO )
root_logger .handlers .clear ()
root_logger .addHandler (_file_rl )
root_logger .addHandler (_console_rl )

logger =logging .getLogger (__name__ )


def install_log_hooks ():
    def _excepthook (exc_type ,exc ,tb ):
        try :
            lines =traceback .format_exception (exc_type ,exc ,tb )
            logger .error ("Uncaught exception:\n%s","".join (lines ))
        except Exception :
            pass 

        try :
            sys .__excepthook__ (exc_type ,exc ,tb )
        except Exception :
            pass 

    try :
        sys .excepthook =_excepthook 
    except Exception :
        pass 

    def _qt_msg_handler (mode ,context ,message ):
        try :
            try :
                msg =str (message )
            except Exception :
                msg =""

            if mode ==QtMsgType .QtCriticalMsg :
                logger .error ("QtCritical: %s",msg )
            elif mode ==QtMsgType .QtFatalMsg :
                logger .critical ("QtFatal: %s",msg )
        except Exception :
            pass 

    try :
        qInstallMessageHandler (_qt_msg_handler )
    except Exception :
        pass 


class ButtonHoverCursorFilter (QObject ):
    def eventFilter (self ,obj ,event ):
        try :
            if isinstance (obj ,QAbstractButton ):
                if event .type ()==QEvent .Type .Enter :
                    obj .setCursor (Qt .CursorShape .PointingHandCursor )
                elif event .type ()==QEvent .Type .Leave :
                    obj .unsetCursor ()
        except Exception :
            pass 
        return super ().eventFilter (obj ,event )

CURRENT_VERSION ='3.0'

def compute_category_counts (tools_list ):
    counts ={}
    counts [""]=len (tools_list )
    for t in tools_list :
        cat =t ["category"]
        counts [cat ]=counts .get (cat ,0 )+1 
    counts ["我的收藏"]=len (get_favorite_tools (tools_list ))
    counts ["最近启动"]=len ([k for k in SETTINGS .get ("recent_tools",[])if any (t ['name']==k [0 ]and t ['category']==k [1 ]for t in tools_list )])
    return counts 

class MainWindow (QMainWindow ):
    _toggle_visibility_signal =pyqtSignal ()
    # _screenshot_signal = pyqtSignal()  # 已禁用截图功能

    def __init__ (self ):
        super ().__init__ ()
        if not ensure_single_instance ():
            sys .exit (0 )

        self ._perf_proc =None 

        self .tools =load_tools ()
        raw_categories =load_categories ()
        self .categories =list (raw_categories )
        for t in self .tools :
            if t ["category"]not in self .categories :
                self .categories .append (t ["category"])
        for special in ("最近启动","我的收藏"):
            if special not in self .categories :
                self .categories .insert (0 ,special )
        self .categories =self ._unique_ordered (self .categories )
        for special in ("最近启动","我的收藏"):
            if special not in self .categories :
                self .categories .insert (0 ,special )

        self .categories .sort (key =self ._cat_sort_key )
        if self .categories !=raw_categories :
            save_categories (self .categories )

        # self.tool_shortcuts = {}  # 已禁用全局热键功能
        # self.load_shortcuts()
        # self.registered_hotkeys = {}

        self .current_category =""
        self .search_text =""

        self .current_page =1 
        self .page_size =16 
        self .total_pages =1 


        self ._is_restarting =False
        self ._dpi_adjusting =False

        self .health_checker =ToolHealthChecker ()
        self ._health_status ={}

        self .init_ui ()


        self ._btn_cursor_filter =ButtonHoverCursorFilter (self )
        QApplication .instance ().installEventFilter (self ._btn_cursor_filter )

        self .init_tray ()
        # self.init_shortcuts()  # 已禁用全局热键功能
        self .load_main_window_state_and_geometry ()
        self ._clamp_to_screen ()

        self ._toggle_visibility_signal .connect (self .toggle_window_visibility )
        # self._screenshot_signal.connect(self.take_screenshot)  # 已禁用截图功能

        QTimer .singleShot (500 ,self .check_tools_health )
        QTimer .singleShot (3000 ,self .check_java_path )

        # self._register_global_hotkeys()  # 已禁用全局热键功能

        QTimer .singleShot (100 ,self .refresh_grid_layout )

    def _unique_ordered (self ,seq ):
        seen =set ()
        seen_add =seen .add 
        return [x for x in seq if not (x in seen or seen_add (x ))]

    def _cat_sort_key (self ,cat ):
        if cat =="最近启动":
            return 0
        if cat =="我的收藏":
            return 1
        return 2

    def showEvent (self ,event ):
        super ().showEvent (event )
        try :
            wh =self .windowHandle ()
            if wh and not hasattr (self ,'_screen_changed_connected'):
                wh .screenChanged .connect (self ._on_screen_changed )
                self ._screen_changed_connected =True
        except Exception :
            pass

    def _on_screen_changed (self ,screen ):
        try :
            if screen is None :
                return
            self ._dpi_adjusting =True
            available =screen .availableGeometry ()
            geo =self .geometry ()

            w =min (geo .width (),available .width ())
            h =min (geo .height (),available .height ())
            x =max (available .left (),min (geo .left (),available .right ()-w ))
            y =max (available .top (),min (geo .top (),available .bottom ()-h ))

            self .setGeometry (x ,y ,w ,h )
            QTimer .singleShot (200 ,self ._end_dpi_adjusting )
        except Exception :
            self ._dpi_adjusting =False

    def _end_dpi_adjusting (self ):
        self ._dpi_adjusting =False
        try :
            self .refresh_grid_layout ()
        except Exception :
            pass

    def _clamp_to_screen (self ):
        try :
            screen =self .screen ()
            if screen is None :
                screen =QApplication .primaryScreen ()
            if screen is None :
                return
            available =screen .availableGeometry ()
            geo =self .geometry ()
            w =min (geo .width (),available .width ())
            h =min (geo .height (),available .height ())
            x =max (available .left (),min (geo .left (),available .right ()-w ))
            y =max (available .top (),min (geo .top (),available .bottom ()-h ))
            self .setGeometry (x ,y ,w ,h )
        except Exception :
            pass

    def init_ui (self ):
        self .setWindowTitle ("天狐渗透工具箱-社区版V4.0")
        self .setWindowIcon (QIcon ("config/fox.ico"))
        self .setWindowFlag (Qt .WindowType .FramelessWindowHint )
        self .resize (1400 ,800 )


        self .setAcceptDrops (True )

        central =QWidget ()
        self .setCentralWidget (central )
        main_lay =QVBoxLayout (central )
        main_lay .setContentsMargins (0 ,0 ,0 ,0 )
        main_lay .setSpacing (0 )

        self .title_bar =TitleBar (self )
        main_lay .addWidget (self .title_bar )

        content_layout =QHBoxLayout ()
        content_layout .setContentsMargins (0 ,0 ,0 ,0 )
        content_layout .setSpacing (20 )

        self .cat_panel =CategoryPanel (self .categories )
        self .cat_panel .setFixedWidth (240 )
        self .cat_panel .category_selected .connect (self .on_cat_selected )
        self .cat_panel .category_renamed .connect (self .on_cat_renamed )
        self .cat_panel .category_deleted .connect (self .on_cat_deleted )
        self .cat_panel .category_added .connect (self .on_cat_added )
        self .cat_panel .category_move .connect (self .on_cat_move )
        content_layout .addWidget (self .cat_panel )

        right_panel =QWidget ()
        rlayout =QVBoxLayout (right_panel )
        rlayout .setContentsMargins (0 ,0 ,0 ,0 )
        rlayout .setSpacing (0 )

        topbar =QWidget ()
        hl =QHBoxLayout (topbar )
        hl .setContentsMargins (10 ,10 ,10 ,10 )

        self .search_bar =SearchBar ()
        self .search_bar .search_changed .connect (self .on_search )
        hl .addWidget (self .search_bar )

        self .shortcut_find =QShortcut (QKeySequence ("Ctrl+F"),self )
        self .shortcut_find .activated .connect (self ._focus_search )

        btn_add =QPushButton ("添加工具")
        btn_add .setObjectName ("noHoverBtn")
        btn_add .setFixedWidth (100 )
        btn_add .clicked .connect (self .add_tool )
        hl .addWidget (btn_add )

        self .btn_notebook =QPushButton ("记事本")
        self .btn_notebook .setObjectName ("noHoverBtn")
        self .btn_notebook .setFixedWidth (80 )
        self .btn_notebook .clicked .connect (self .open_notebook )
        hl .addWidget (self .btn_notebook )

        btn_set =QPushButton ("设置")
        btn_set .setObjectName ("noHoverBtn")
        btn_set .setFixedWidth (80 )
        btn_set .clicked .connect (self .show_settings )
        hl .addWidget (btn_set )

        # self.btn_terminal = QPushButton("终端")  # 已禁用终端功能
        # self.btn_terminal.setObjectName("noHoverBtn")
        # self.btn_terminal.setMinimumWidth(60)
        # self.btn_terminal.clicked.connect(self.toggle_terminal)
        # hl.addWidget(self.btn_terminal)

        self .btn_batch =QPushButton ("批量模式")
        self .btn_batch .setObjectName ("noHoverBtn")
        self .btn_batch .setFixedWidth (100 )
        self .btn_batch .clicked .connect (self .toggle_batch_mode )
        hl .addWidget (self .btn_batch )

        self .btn_run_batch =QPushButton ("运行选中")
        self .btn_run_batch .setObjectName ("noHoverBtn")
        self .btn_run_batch .setFixedWidth (100 )
        self .btn_run_batch .clicked .connect (self .do_batch_run )
        self .btn_run_batch .hide ()
        hl .addWidget (self .btn_run_batch )

        btn_import =QPushButton ("导入")
        btn_import .setObjectName ("noHoverBtn")
        btn_import .setFixedWidth (70 )
        btn_import .clicked .connect (self .import_data )
        hl .addWidget (btn_import )

        btn_export =QPushButton ("导出")
        btn_export .setObjectName ("noHoverBtn")
        btn_export .setFixedWidth (70 )
        btn_export .clicked .connect (self .export_data )
        hl .addWidget (btn_export )

        topbar .setLayout (hl )
        rlayout .addWidget (topbar )

        self .tool_grid =ModernToolGrid ()
        self .tool_grid .tool_run .connect (self .run_tool )
        self .tool_grid .tool_edit .connect (self .edit_tool )
        self .tool_grid .tool_delete .connect (self .delete_tool )
        self .tool_grid .favorite_changed .connect (self .on_favorite_changed )
        self .tool_grid .batch_run_requested .connect (self .run_tools_batch )
        rlayout .addWidget (self .tool_grid )


        self .page_widget =QWidget ()
        page_layout =QHBoxLayout (self .page_widget )
        page_layout .setContentsMargins (0 ,5 ,0 ,5 )

        self .btn_prev =QPushButton ("上一页")
        self .btn_prev .setObjectName ("noHoverBtn")
        self .btn_prev .setFixedWidth (80 )
        self .btn_prev .clicked .connect (self .prev_page )

        self .lb_page =QLabel ("1 / 1")
        self .lb_page .setAlignment (Qt .AlignmentFlag .AlignCenter )

        self .btn_next =QPushButton ("下一页")
        self .btn_next .setObjectName ("noHoverBtn")
        self .btn_next .setFixedWidth (80 )
        self .btn_next .clicked .connect (self .next_page )

        self .ed_page_jump =QLineEdit ()
        self .ed_page_jump .setFixedWidth (50 )
        self .ed_page_jump .setPlaceholderText ("页码")
        self .ed_page_jump .setAlignment (Qt .AlignmentFlag .AlignCenter )
        self .ed_page_jump .returnPressed .connect (self .jump_to_page )

        self .btn_jump =QPushButton ("跳转")
        self .btn_jump .setObjectName ("noHoverBtn")
        self .btn_jump .setFixedWidth (60 )
        self .btn_jump .clicked .connect (self .jump_to_page )

        page_layout .addStretch ()
        page_layout .addWidget (self .btn_prev )
        page_layout .addWidget (self .lb_page )
        page_layout .addWidget (self .btn_next )
        page_layout .addSpacing (20 )
        page_layout .addWidget (self .ed_page_jump )
        page_layout .addWidget (self .btn_jump )
        page_layout .addStretch ()

        rlayout .addWidget (self .page_widget )

        content_layout .addWidget (right_panel )
        main_lay .addLayout (content_layout )

        self .apply_theme ()
        self .update_cat_panel ()
        self .update_tool_grid ()

        self .init_perf_monitor ()


    def init_perf_monitor (self ):
        try :
            import psutil 
            self ._perf_proc =psutil .Process (os .getpid ())
            try :
                self ._perf_proc .cpu_percent (None )
            except Exception :
                pass 
        except Exception :
            self ._perf_proc =None 

        self ._perf_timer =QTimer (self )
        self ._perf_timer .setInterval (10000 )
        self ._perf_timer .timeout .connect (self .update_perf_monitor )
        self ._perf_timer .start ()
        self .update_perf_monitor ()


    def update_perf_monitor (self ):
        try :
            target =None 
            try :
                target =getattr (getattr (self ,"title_bar",None ),"perf_label",None )
            except Exception :
                target =None 

            if target is None :
                return 

            if self ._perf_proc is None :
                target .setText ("CPU N/A | 内存 N/A")
                return 

            cpu =0.0 
            mem_mb =0.0 
            mem_pct =0.0 
            try :
                cpu =float (self ._perf_proc .cpu_percent (None ))
            except Exception :
                cpu =0.0 
            try :
                mem_mb =float (self ._perf_proc .memory_info ().rss )/1024.0 /1024.0 
            except Exception :
                mem_mb =0.0 

            try :
                import psutil 
                vm =psutil .virtual_memory ()
                if getattr (vm ,"total",0 ):
                    mem_pct =(float (self ._perf_proc .memory_info ().rss )/float (vm .total ))*100.0 
            except Exception :
                mem_pct =0.0 

            target .setText (f"CPU {cpu:.1f}% | 内存 {mem_mb:.0f}MB({mem_pct:.1f}%)")
        except Exception :
            try :
                target =getattr (getattr (self ,"title_bar",None ),"perf_label",None )
                if target is not None :
                    target .setText ("CPU N/A | 内存 N/A")
            except Exception :
                pass 

    def _focus_search (self ):
        try :
            self .search_bar .search_input .setFocus ()
            self .search_bar .search_input .selectAll ()
        except Exception :
            pass 

    def dragEnterEvent (self ,event ):
        try :
            if event .mimeData ().hasUrls ():
                event .acceptProposedAction ()
                return 
        except Exception :
            pass 
        event .ignore ()

    def dropEvent (self ,event ):
        try :
            if not event .mimeData ().hasUrls ():
                event .ignore ()
                return 

            paths =[]
            for u in event .mimeData ().urls ():
                try :
                    p =u .toLocalFile ()
                except Exception :
                    p =""
                if p :
                    paths .append (p )

            if not paths :
                event .ignore ()
                return 


            self ._open_add_tool_dialog_with_path (paths [0 ])
            event .acceptProposedAction ()
        except Exception as e :
            QMessageBox .warning (self ,"拖拽添加",str (e ))
            event .ignore ()

    def _open_add_tool_dialog_with_path (self ,path :str ):

        if getattr (self ,"current_category","")in ("","最近启动","我的收藏"):
            QMessageBox .information (self ,"提示","此工具分类不允许拖拽添加程序的工具卡片")
            return 


        if not os .path .isfile (path ):
            QMessageBox .information (self ,"提示","仅支持拖拽程序文件添加工具卡片")
            return 

        ext =os .path .splitext (path )[1 ].lower ()
        allowed ={".vbs",".bat",".py",".jar",".exe"}
        if ext not in allowed :
            QMessageBox .information (self ,"提示","仅支持拖拽 vbs/bat/py/jar/exe 文件")
            return 

        # self.disable_all_hotkeys()  # 已禁用全局热键功能
        try :
            diag =ToolDialog (self .categories ,None ,self )

            base =os .path .basename (path .rstrip ("\\/"))
            name =os .path .splitext (base )[0 ]if os .path .isfile (path )else base 
            if hasattr (diag ,"ed_name"):
                diag .ed_name .setText (name )
            if hasattr (diag ,"ed_path"):
                diag .ed_path .setText (path )
            if hasattr (diag ,"cb_cat")and getattr (self ,"current_category","")not in ("","最近启动","我的收藏"):
                diag .cb_cat .setCurrentText (self .current_category )


            if hasattr (diag ,"cb_type"):
                type_map ={
                ".py":"Python",
                ".jar":"JAVA8",
                ".exe":"GUI应用",
                ".bat":"批处理",
                ".vbs":"批处理",
                }
                want =type_map .get (ext )
                if want :
                    diag .cb_type .setCurrentText (want )

            if diag .exec ():
                td =diag .get_tool_data ()
                if td ["type"]=="网页":
                    if not td ["name"]or not td ["url"]or not td ["category"]:
                        QMessageBox .warning (self ,"错误","请填写所有必填字段")
                    else :
                        if not self ._add_new_tool (td ):
                            QMessageBox .warning (self ,"错误","保存工具数据失败")
                else :
                    if not td ["name"]or not td ["category"]or not td ["path"]:
                        QMessageBox .warning (self ,"错误","请填写所有必填字段")
                    else :
                        if check_environment (td ["type"]):
                            if not self ._add_new_tool (td ):
                                QMessageBox .warning (self ,"错误","保存工具数据失败")

                # if diag.shortcut_key:  # 已禁用全局热键功能
                #     self.tool_shortcuts[td['name']] = diag.shortcut_key
                #     self.save_shortcuts()
        finally :
            # self.re_register_hotkeys()  # 已禁用全局热键功能
            self .update_tool_grid ()

    def refresh_grid_layout (self ):
        try :
            self .tool_grid .adjust_card_size ()
            self ._recompute_page_size_if_needed ()
        except Exception as e :
            logger .error (f"刷新卡片布局异常: {e}")

    def _recompute_page_size_if_needed (self ):
        try :
            if SETTINGS .get ("display_mode","scroll")!="paged":
                return 


            if not self .isMaximized ():
                new_page_size =20 
            else :
                grid_size =self .tool_grid .gridSize ()
                if grid_size .width ()<=0 or grid_size .height ()<=0 :
                    return 
                vp =self .tool_grid .viewport ().size ()
                cols =max (1 ,vp .width ()//grid_size .width ())
                rows =max (1 ,vp .height ()//grid_size .height ())
                new_page_size =max (1 ,cols *rows )

            if new_page_size !=self .page_size :
                self .page_size =new_page_size 
                self .current_page =1 
                self .update_tool_grid ()
        except Exception as e :
            logger .error (f"自适应分页数量异常: {e}")

    def resizeEvent (self ,e ):
        super ().resizeEvent (e )
        if getattr (self ,'_dpi_adjusting',False ):
            return
        self ._recompute_page_size_if_needed ()

    def prev_page (self ):
        if self .current_page >1 :
            self .current_page -=1 
            self .update_tool_grid ()

    def next_page (self ):
        if self .current_page <self .total_pages :
            self .current_page +=1 
            self .update_tool_grid ()

    def jump_to_page (self ):
        txt =self .ed_page_jump .text ().strip ()
        if not txt .isdigit ():
            return 
        val =int (txt )
        if 1 <=val <=self .total_pages :
            self .current_page =val 
            self .update_tool_grid ()
            self .ed_page_jump .clear ()
        else :
            msg =QMessageBox (self )
            msg .setWindowTitle ("提示")
            msg .setText (f"页码超出范围 (1-{self.total_pages})")
            msg .setIcon (QMessageBox .Icon .Warning )
            ok_btn =msg .addButton ("确定",QMessageBox .ButtonRole .AcceptRole )
            msg .setDefaultButton (ok_btn )
            msg .exec ()

    def import_data (self ):
        try :
            path ,_ =QFileDialog .getOpenFileName (self ,"选择导入文件","","JSON Files (*.json)")
            if path :
                mode ,ok =QInputDialog .getItem (self ,"导入方式","请选择导入方式：",["合并","覆盖"],0 ,False )
                if ok :
                    import_all_data (path ,"overwrite"if mode =="覆盖"else "merge")
                    QMessageBox .information (self ,"导入","导入完成，请重启或刷新")
                    self .reload_data ()
        except Exception as e :
            QMessageBox .warning (self ,"导入错误",str (e ))

    def export_data (self ):
        try :
            path ,_ =QFileDialog .getSaveFileName (self ,"导出为","","JSON Files (*.json)")
            if path :
                export_all_data (path )
                QMessageBox .information (self ,"导出","导出完成！")
        except Exception as e :
            QMessageBox .warning (self ,"导出错误",str (e ))


    def reload_data (self ):
        self .tools =load_tools ()
        self .categories =load_categories ()
        self .apply_theme ()
        self .update_cat_panel ()
        self .update_tool_grid ()
        self .refresh_grid_layout ()

    def apply_theme (self ):
        from config import STYLESHEET 
        try :
            app =QApplication .instance ()
            if app is not None :
                app .setStyleSheet (STYLESHEET )
            else :
                self .setStyleSheet (STYLESHEET )
        except Exception :
            self .setStyleSheet (STYLESHEET )


        try :
            from utils import install_liquid_glass_animations 
            install_liquid_glass_animations (self )
        except Exception :
            pass 

        try :
            from utils import install_red_blue_glass_popup_blur 
            install_red_blue_glass_popup_blur (self )
        except Exception :
            pass 


        theme_name =SETTINGS .get ("theme","dark")
        hwnd =int (self .winId ())
        effect =WindowEffect ()

        if theme_name in ("liquid_glass","red_blue_glass","custom_image"):

            effect .set_acrylic_effect (hwnd ,is_dark =True )
        else :
            effect .remove_background_effect (hwnd )

    def paintEvent (self ,event ):
        if SETTINGS .get ("theme")=="custom_image":
            image_path =SETTINGS .get ("custom_bg_path","")
            if image_path and os .path .isfile (image_path ):
                painter =QPainter (self )
                pix =QPixmap (image_path )
                if not pix .isNull ():
                    scaled_pix =pix .scaled (self .width (),self .height (),
                    Qt .AspectRatioMode .KeepAspectRatioByExpanding ,
                    Qt .TransformationMode .SmoothTransformation )
                    x =(self .width ()-scaled_pix .width ())//2 
                    y =(self .height ()-scaled_pix .height ())//2 
                    painter .drawPixmap (x ,y ,scaled_pix )
        super ().paintEvent (event )


    def update_cat_panel (self ):
        ccount =compute_category_counts (self .tools )
        self .cat_panel .categories =self .categories 
        self .cat_panel .update_categories (self .categories ,ccount )


        try :
            from utils import install_liquid_glass_animations 
            install_liquid_glass_animations (self .cat_panel )
        except Exception :
            pass 

    def update_tool_grid (self ):

        from utils import get_favorite_tools ,get_recent_tools ,fuzzy_search 

        category =self .current_category 
        search_text =self .search_text 

        if category =="我的收藏":
            filtered =get_favorite_tools (self .tools )
        elif category =="最近启动":
            filtered =get_recent_tools (self .tools )
        elif category :
            filtered =[t for t in self .tools if t ['category']==category ]
        else :
            filtered =self .tools 

        if search_text :
            filtered =fuzzy_search (filtered ,search_text )

        seen =set ()
        final =[]
        for t in filtered :
            k =(t ['name'],t ['category'])
            if k not in seen :
                seen .add (k )
                final .append (t )


        final .sort (key =lambda x :(-float (x .get ("weight",0 )or 0 ),str (x .get ('name',''))))


        disp =SETTINGS .get ("display_mode","scroll")

        if disp =="paged":
            self .page_widget .show ()
            total_items =len (final )
            if total_items ==0 :
                self .total_pages =1 
                self .current_page =1 
                display_tools =[]
            else :
                self .total_pages =(total_items +self .page_size -1 )//self .page_size 
                if self .current_page >self .total_pages :
                    self .current_page =self .total_pages 
                if self .current_page <1 :
                    self .current_page =1 

                start_idx =(self .current_page -1 )*self .page_size 
                end_idx =start_idx +self .page_size 
                display_tools =final [start_idx :end_idx ]

            self .lb_page .setText (f"{self.current_page} / {self.total_pages}")
            self .btn_prev .setEnabled (self .current_page >1 )
            self .btn_next .setEnabled (self .current_page <self .total_pages )
        else :
            self .page_widget .hide ()
            display_tools =final

        for tool in display_tools :
            tool ["_health"]=self ._health_status .get (tool .get ("name",""),"ok")

        self .tool_grid .set_final_tools (display_tools )


        try :
            from utils import animate_liquid_glass_fade 
            animate_liquid_glass_fade (self .tool_grid )
        except Exception :
            pass 
        self .refresh_grid_layout ()

    def on_cat_selected (self ,cat ):
        self .current_category =cat 
        self .current_page =1 
        self .update_tool_grid ()

    def on_cat_renamed (self ,old_name ,new_name ):
        old_name =str (old_name or "").strip ()
        new_name =str (new_name or "").strip ()
        if not new_name :
            QMessageBox .warning (self ,"错误","分类名称不能为空")
            return 
        norm =new_name .casefold ()
        if any (str (x ).strip ().casefold ()==norm for x in (self .categories or [])if str (x ).strip ()!=old_name ):
            QMessageBox .warning (self ,"错误",f"分类 '{new_name}' 已存在！")
            return 

        if old_name in self .categories :
            idx =self .categories .index (old_name )
            self .categories [idx ]=new_name 
        if save_tools (self .tools ):
            self .update_cat_panel ()
            self .update_tool_grid ()
        else :
            QMessageBox .warning (self ,"错误","保存工具数据失败")

    def on_cat_deleted (self ,cat ):
        if cat in ("我的收藏","最近启动"):
            QMessageBox .warning (self ,"提示","此分区不允许删除")
            return 
        tools_in_category =[t for t in self .tools if t ["category"]==cat ]
        if not tools_in_category :
            if cat in self .categories :
                self .categories .remove (cat )
                save_categories (self .categories )
                self .update_cat_panel ()
            return 
        else :
            msg =QMessageBox (self )
            msg .setWindowTitle ("确认删除")
            msg .setIcon (QMessageBox .Icon .Question )
            msg .setText (f"分类 '{cat}' 下共有 {len(tools_in_category)} 个工具，删除该分类会一并删除这些工具。\n是否继续？")
            msg .setStandardButtons (QMessageBox .StandardButton .Yes |QMessageBox .StandardButton .No )
            result =msg .exec ()

            if result ==QMessageBox .StandardButton .Yes :
                self .tools =[t for t in self .tools if t ["category"]!=cat ]
                if cat in self .categories :
                    self .categories .remove (cat )
                if save_tools (self .tools )and save_categories (self .categories ):
                    self .current_category =""
                    self .update_cat_panel ()
                    self .update_tool_grid ()
                else :
                    QMessageBox .warning (self ,"错误","保存数据失败，无法完成删除操作。")

    def on_cat_move (self ,cat ,direction ):
        if cat not in self .categories or cat in ("我的收藏","最近启动"):
            return 
        idx =self .categories .index (cat )
        new_idx =idx +direction 
        min_idx =2 if "最近启动"in self .categories and "我的收藏"in self .categories else 0 
        if new_idx <min_idx or new_idx >=len (self .categories ):
            return 
        self .categories .pop (idx )
        self .categories .insert (new_idx ,cat )
        save_categories (self .categories )
        self .update_cat_panel ()

    def on_cat_added (self ,_ ):
        new_cat ,ok =QInputDialog .getText (self ,"新建分类","请输入分类名称:")
        if ok and new_cat .strip ():
            new_cat =new_cat .strip ()

            norm =new_cat .casefold ()
            if any (str (x ).strip ().casefold ()==norm for x in (self .categories or [])):
                QMessageBox .warning (self ,"错误",f"分类 '{new_cat}' 已存在！")
                return 

            self .categories .append (new_cat )
            self .categories =sorted (set (self .categories ),key =self ._cat_sort_key )
            save_categories (self .categories )
            self .update_cat_panel ()

    def on_search (self ,txt ):
        self .search_text =(txt or "").strip ()
        self .current_page =1
        self .update_tool_grid ()
        self .refresh_grid_layout ()

    # def disable_all_hotkeys(self):  # 已禁用全局热键功能
    #     for tool_name, hotkey in list(self.registered_hotkeys.items()):
    #         try:
    #             keyboard.remove_hotkey(hotkey)
    #         except:
    #             pass
    #     self.registered_hotkeys.clear()

    # def re_register_hotkeys(self):  # 已禁用全局热键功能
    #     for nm, hk in self.tool_shortcuts.items():
    #         self.register_hotkey(nm, hk)

    def add_tool (self ):
        # self.disable_all_hotkeys()  # 已禁用全局热键功能
        try :
            diag =ToolDialog (self .categories ,None ,self )
            if diag .exec ():
                td =diag .get_tool_data ()
                if td ["type"]=="网页":
                    if not td ["name"]or not td ["url"]or not td ["category"]:
                        QMessageBox .warning (self ,"错误","请填写所有必填字段")
                    else :
                        if not self ._add_new_tool (td ):
                            QMessageBox .warning (self ,"错误","保存工具数据失败")
                else :
                    if not td ["name"]or not td ["category"]or not td ["path"]:
                        QMessageBox .warning (self ,"错误","请填写所有必填字段")
                    else :
                        if check_environment (td ["type"]):
                            if not self ._add_new_tool (td ):
                                QMessageBox .warning (self ,"错误","保存工具数据失败")

                # if diag.shortcut_key:  # 已禁用全局热键功能
                #     self.tool_shortcuts[td['name']] = diag.shortcut_key
                #     self.save_shortcuts()
        except Exception as e :
            QMessageBox .warning (self ,"添加工具异常",str (e ))
        # self.re_register_hotkeys()  # 已禁用全局热键功能
        self .update_tool_grid ()

    def _add_new_tool (self ,td ):

        td_name =str (td .get ('name','')).strip ()
        norm =td_name .casefold ()
        for ex in (self .tools or []):
            ex_name =str (ex .get ('name','')).strip ()
            if ex_name and ex_name .casefold ()==norm :
                QMessageBox .warning (self ,"错误","已存在同名工具，工具名称必须唯一")
                return True 

        self .tools .append (td )
        if td ["category"]not in self .categories :
            self .categories .append (td ["category"])
            self .categories =sorted (set (self .categories ),key =self ._cat_sort_key )
            save_categories (self .categories )

        if save_tools (self .tools ):
            self .update_cat_panel ()
            self .update_tool_grid ()
            self ._health_status [td .get ("name","")]=self .health_checker .check_tool (td )
            self .update_tool_grid ()
            return True
        return False 

    def edit_tool (self ,tool_data ):
        # self.disable_all_hotkeys()  # 已禁用全局热键功能
        try :
            diag =ToolDialog (self .categories ,tool_data ,self )
            old_name =tool_data ['name']
            if diag .exec ():
                newinfo =diag .get_tool_data ()


                new_name =str (newinfo .get ('name','')).strip ()
                norm =new_name .casefold ()
                idx =self .tools .index (tool_data )
                for i ,ex in enumerate (self .tools or []):
                    if i ==idx :
                        continue 
                    ex_name =str (ex .get ('name','')).strip ()
                    if ex_name and ex_name .casefold ()==norm :
                        QMessageBox .warning (self ,"错误","已存在同名工具，工具名称必须唯一")
                        return 
                self .tools [idx ]=newinfo 

                if not save_tools (self .tools ):
                    QMessageBox .warning (self ,"错误","保存失败！")
                else :
                    self .update_cat_panel ()
                    self .update_tool_grid ()

                # 以下热键相关代码已禁用
                # new_short = diag.shortcut_key
                # if old_name != newinfo['name']:
                #     if old_name in self.tool_shortcuts:
                #         self.tool_shortcuts.pop(old_name, None)
                #     if old_name in self.registered_hotkeys:
                #         self.remove_hotkey(old_name)
                # if new_short:
                #     self.tool_shortcuts[newinfo['name']] = new_short
                # else:
                #     if newinfo['name'] in self.tool_shortcuts:
                #         self.tool_shortcuts.pop(newinfo['name'], None)
                #     self.remove_hotkey(newinfo['name'])
                # self.save_shortcuts()
        except Exception as e :
            QMessageBox .warning (self ,"编辑工具异常",str (e ))
        # self.re_register_hotkeys()  # 已禁用全局热键功能
        self .check_tools_health ()
        self .update_tool_grid ()

    def delete_tool (self ,tool_data ):
        msg =QMessageBox (self )
        msg .setWindowTitle ("确认删除")
        msg .setText (f"确定删除工具 '{tool_data['name']}' 吗？")
        msg .setIcon (QMessageBox .Icon .Question )
        msg .setStandardButtons (QMessageBox .StandardButton .Yes |QMessageBox .StandardButton .No )
        r =msg .exec ()
        if r ==QMessageBox .StandardButton .Yes :
            cat =tool_data ["category"]
            self .tools .remove (tool_data )

            if not save_tools (self .tools ):
                QMessageBox .warning (self ,"错误","保存工具数据失败")
                return 

            nm =tool_data ['name']
            # if nm in self.tool_shortcuts:  # 已禁用全局热键功能
            #     self.tool_shortcuts.pop(nm, None)
            # self.remove_hotkey(nm)

            remain =[t for t in self .tools if t ["category"]==cat ]
            if not remain and cat not in DEFAULT_CATEGORIES :
                if cat in self .categories :
                    self .categories .remove (cat )
                save_categories (self .categories )

            self .update_cat_panel ()
            self .update_tool_grid ()
            self .refresh_grid_layout ()

    def run_tool (self ,tool_data ):
        try :
            run_tool (tool_data )
        except Exception as e :
            QMessageBox .warning (self ,"错误",f"运行失败:{e}")

    def run_tools_batch (self ,tools ):
        try :
            succ =run_tools_batch (tools )
            QMessageBox .information (self ,"批量运行",f"已启动 {succ} 个工具")
        except Exception as e :
            QMessageBox .warning (self ,"批量运行",f"发生异常: {e}")

    def on_favorite_changed (self ,tool_data ,is_fav ):
        self .update_cat_panel ()
        self .update_tool_grid ()
        self .refresh_grid_layout ()

    # def load_shortcuts(self):  # 已禁用全局热键功能
    #     s = QSettings("config/shortcuts.ini", QSettings.Format.IniFormat)
    #     for t in self.tools:
    #         val = s.value(f"shortcuts/{t['name']}", "")
    #         if val:
    #             self.tool_shortcuts[t['name']] = val

    # def save_shortcuts(self):  # 已禁用全局热键功能
    #     s = QSettings("config/shortcuts.ini", QSettings.Format.IniFormat)
    #     all_keys = s.allKeys()
    #     for k in all_keys:
    #         if k.startswith("shortcuts/"):
    #             s.remove(k)
    #     for nm, val in self.tool_shortcuts.items():
    #         s.setValue(f"shortcuts/{nm}", val)
    #     s.sync()

    # def init_shortcuts(self):  # 已禁用全局热键功能
    #     for nm, hk in self.tool_shortcuts.items():
    #         self.register_hotkey(nm, hk)

    # def register_hotkey(self, tool_name: str, hotkey: str):  # 已禁用全局热键功能
    #     self.remove_hotkey(tool_name)
    #     lower_key = hotkey.lower()
    #     for exist_tool, exist_key in self.registered_hotkeys.items():
    #         if exist_key == lower_key and exist_tool != tool_name:
    #             QMessageBox.warning(
    #                 self,
    #                 "快捷键冲突",
    #                 f"快捷键 '{hotkey}' 已被【{exist_tool}】使用，无法设置给【{tool_name}】。"
    #             )
    #             return
    #     try:
    #         def _callback(tn=tool_name):
    #             found = [t for t in self.tools if t['name'] == tn]
    #             if found:
    #                 self.run_tool(found[0])
    #         keyboard.add_hotkey(lower_key, _callback)
    #         self.registered_hotkeys[tool_name] = lower_key
    #     except Exception as e:
    #         logger.error(f"注册热键失败: {hotkey} - {e}")

    # def remove_hotkey(self, tool_name: str):  # 已禁用全局热键功能
    #     if tool_name in self.registered_hotkeys:
    #         old_hk = self.registered_hotkeys[tool_name]
    #         try:
    #             keyboard.remove_hotkey(old_hk)
    #         except:
    #             pass
    #         self.registered_hotkeys.pop(tool_name, None)

    # def toggle_terminal(self):  # 已禁用终端功能
    #     if not hasattr(self, '_terminal_panel'):
    #         self._setup_terminal_panel()
    #     if self._terminal_panel.isVisible():
    #         self._terminal_panel.hide()
    #         self.btn_terminal.setText("终端")
    #     else:
    #         self._terminal_panel.show()
    #         self.btn_terminal.setText("关闭终端")
    #         if self._terminal_tabs.terminal_count() == 0:
    #             from config import SETTINGS
    #             shell = SETTINGS.get("terminal_default_shell", "cmd")
    #             self._terminal_tabs.add_terminal(shell_type=shell)

    # def _setup_terminal_panel(self):  # 已禁用终端功能
    #     from PyQt6.QtWidgets import QDockWidget
    #     from views.terminal_tab_widget import TerminalTabWidget
    #     self._terminal_panel = QWidget(self)
    #     layout = QVBoxLayout(self._terminal_panel)
    #     layout.setContentsMargins(0, 0, 0, 0)
    #     layout.setSpacing(0)
    #     self._terminal_tabs = TerminalTabWidget(self._terminal_panel)
    #     layout.addWidget(self._terminal_tabs)
    #     self._terminal_panel.setLayout(layout)
    #     self._terminal_panel.setMinimumHeight(200)
    #     self._terminal_panel.setMaximumHeight(500)
    #     self._terminal_panel.hide()
    #     right_panel = self.tool_grid.parentWidget()
    #     if right_panel:
    #         rlayout = right_panel.layout()
    #         if rlayout:
    #             idx = rlayout.indexOf(self.tool_grid)
    #             rlayout.insertWidget(idx + 1, self._terminal_panel)

    def show_settings (self ):
        diag =SettingsDialog (self )
        diag .settings_changed .connect (self .on_settings_changed )

        try :
            from utils import install_liquid_glass_animations 
            install_liquid_glass_animations (diag )
        except Exception :
            pass 

        diag .exec ()

    def on_settings_changed (self ,new_s ):
        import config 
        from config import SETTINGS ,load_theme 
        old_theme =SETTINGS .get ("theme","dark")
        old_exit_mode =SETTINGS .get ("exit_mode","ask")
        new_theme =new_s .get ("theme","dark")
        new_exit_mode =new_s .get ("exit_mode","ask")

        SETTINGS .clear ()
        SETTINGS .update (new_s )
        global THEME 
        THEME =load_theme (SETTINGS .get ("theme","dark"))
        config .THEME =THEME 


        need_restart =(old_theme !=new_theme )or (old_exit_mode !=new_exit_mode )

        if need_restart :
            msg =QMessageBox (self )
            msg .setWindowTitle ("重启确认")
            msg .setIcon (QMessageBox .Icon .Information )
            msg .setText ("退出模式或主题已更改，需要重启才能生效。程序将立即重启。")
            ok_btn =msg .addButton ("确定",QMessageBox .ButtonRole .AcceptRole )
            ok_btn .setObjectName ("dialogBtn")
            msg .setDefaultButton (ok_btn )
            msg .exec ()
            self .restart_application ()
            return 


        self .apply_theme ()
        self .update_tool_grid ()
        self .refresh_grid_layout ()

        # self._register_global_hotkeys()  # 已禁用全局热键功能

    # def _register_global_hotkeys(self):  # 已禁用全局热键功能
    #     for hk_name in ("screenshot_hotkey", "quick_open_hotkey"):
    #         old_val = getattr(self, f"_{hk_name}_registered", "")
    #         if old_val:
    #             try:
    #                 keyboard.remove_hotkey(old_val)
    #             except Exception:
    #                 pass
    #     ss_val = SETTINGS.get("screenshot_hotkey", "")
    #     if ss_val:
    #         try:
    #             keyboard.add_hotkey(ss_val, lambda: self._screenshot_signal.emit())
    #             self._screenshot_hotkey_registered = ss_val
    #         except Exception as e:
    #             logger.warning(f"注册截图快捷键失败: {e}")
    #             self._screenshot_hotkey_registered = ""
    #     else:
    #         self._screenshot_hotkey_registered = ""
    #     qo_val = SETTINGS.get("quick_open_hotkey", "")
    #     if qo_val:
    #         try:
    #             keyboard.add_hotkey(qo_val, lambda: self._toggle_visibility_signal.emit())
    #             self._quick_open_hotkey_registered = qo_val
    #         except Exception as e:
    #             logger.warning(f"注册快捷启动快捷键失败: {e}")
    #             self._quick_open_hotkey_registered = ""
    #     else:
    #         self._quick_open_hotkey_registered = ""

    # def take_screenshot(self):  # 已禁用截图功能
    #     try:
    #         from core.screenshot import ScreenshotOverlay
    #         self._screenshot_overlay = ScreenshotOverlay(callback=self._on_screenshot_taken)
    #         self._screenshot_overlay.show_and_capture()
    #     except Exception as e:
    #         logger.error(f"截图失败: {e}", exc_info=True)

    # def _on_screenshot_taken(self, filepath):  # 已禁用截图功能
    #     try:
    #         logger.info(f"截图已保存: {filepath}")
    #     except Exception:
    #         pass

    def toggle_window_visibility (self ):
        try :
            if self .isVisible ():
                if self .windowState ()&Qt .WindowState .WindowMinimized :
                    self .showNormal ()
                    self .activateWindow ()
                    self .raise_()
                else :
                    self .showMinimized ()
            else :
                self .showNormal ()
                self .activateWindow ()
                self .raise_()
        except Exception as e :
            logger .error (f"切换窗口可见性失败: {e}")

    def restart_application (self ):
        self ._is_restarting =True 

        try :
            from config import SETTINGS as _SETTINGS 
            save_settings (_SETTINGS )
        except Exception :

            pass 


        import subprocess 
        import sys 


        loader_path =os .path .join (os .path .dirname (os .path .abspath (__file__ )),"loader.py")
        python_exe =sys .executable 


        if sys .platform .startswith ("win"):

            subprocess .Popen ([python_exe ,loader_path ],creationflags =subprocess .CREATE_NEW_PROCESS_GROUP ,close_fds =True )
        else :

            pid =os .fork ()
            if pid >0 :

                os ._exit (0 )
            else :

                os .setsid ()
                pid =os .fork ()
                if pid >0 :
                    os ._exit (0 )
                else :

                    os .execv (python_exe ,[python_exe ,loader_path ])


        self .force_quit ()

    def check_java_path (self ):
        try :
            validate_java_path ()
        except Exception as e :
            QMessageBox .warning (self ,"Java路径",f"检测Java路径失败: {e}")

    def init_tray (self ):
        self .tray_icon =QSystemTrayIcon (self )
        self .tray_icon .setIcon (QIcon ("config/fox.ico"))
        m =QMenu ()

        try :
            anim =QVariantAnimation (m )
            anim .setDuration (140 )
            anim .setEasingCurve (QEasingCurve .Type .OutCubic )

            def _on_val (v ):
                t =float (v )
                try :
                    m .setWindowOpacity (t )
                except Exception :
                    pass 
                try :
                    p =m .pos ()
                    m .move (p .x (),p .y ()+int (6 *(1.0 -t )))
                except Exception :
                    pass 

            anim .valueChanged .connect (_on_val )

            def _start_anim ():
                try :
                    anim .stop ()
                except Exception :
                    pass 
                try :
                    m .setWindowOpacity (0.0 )
                except Exception :
                    return 
                anim .setStartValue (0.0 )
                anim .setEndValue (1.0 )
                anim .start ()

            m .aboutToShow .connect (_start_anim )
        except Exception :
            pass 

        act_show =m .addAction ("显示主窗口")
        act_show .triggered .connect (self .show_and_focus )
        act_exit =m .addAction ("退出程序")
        act_exit .triggered .connect (self .force_quit )
        self .tray_icon .setContextMenu (m )
        self .tray_icon .activated .connect (self .on_tray_activated )
        self .tray_icon .show ()

    def show_and_focus (self ):
        self .show ()
        self .tray_icon .hide ()

    def on_tray_activated (self ,reason ):
        if reason ==QSystemTrayIcon .ActivationReason .DoubleClick :
            self .show_and_focus ()

    def _cleanup_before_exit (self ):

        if getattr (self ,"_is_exiting",False ):
            return 
        self ._is_exiting =True 

        # try:  # 已禁用全局热键功能
        #     self.disable_all_hotkeys()
        # except Exception:
        #     pass
        # try:
        #     keyboard.unhook_all_hotkeys()
        # except Exception:
        #     pass
        # try:
        #     keyboard.unhook_all()
        # except Exception:
        #     pass

        try :
            if hasattr (self ,"tray_icon")and self .tray_icon :
                try :
                    self .tray_icon .hide ()
                except Exception :
                    pass 
        except Exception :
            pass 

    def force_quit (self ):
        try :
            self ._cleanup_before_exit ()
        except Exception :
            pass 
        try :
            QApplication .quit ()
        except Exception :
            pass 

        os ._exit (0 )

    def closeEvent (self ,e ):
        # if hasattr(self, '_terminal_tabs') and self._terminal_tabs.terminal_count() > 0:  # 已禁用终端功能
        #     if not self._terminal_tabs.close_all_terminals():
        #         e.ignore()
        #         return
        save_main_window_geometry (self .saveGeometry ())
        save_main_window_state (self .saveState ())


        if getattr (self ,"_is_restarting",False ):
            e .accept ()
            self .force_quit ()
            return 

        mode =SETTINGS .get ("exit_mode","ask")
        if mode =="ask":
            msg =QMessageBox (self )
            msg .setWindowTitle ("退出确认")
            msg .setText ("确定要退出吗？")
            msg .setIcon (QMessageBox .Icon .Question )
            b1 =msg .addButton ("最小化到托盘",QMessageBox .ButtonRole .ActionRole )
            b2 =msg .addButton ("退出程序",QMessageBox .ButtonRole .AcceptRole )
            b3 =msg .addButton ("取消",QMessageBox .ButtonRole .RejectRole )
            msg .setDefaultButton (b3 )
            for btn in (b1 ,b2 ,b3 ):
                btn .setObjectName ("dialogBtn")
            msg .exec ()
            if msg .clickedButton ()==b1 :
                e .ignore ()
                self .hide ()
                self .tray_icon .show ()
            elif msg .clickedButton ()==b2 :
                e .accept ()
                self .force_quit ()
            else :
                e .ignore ()
        elif mode =="tray":
            e .ignore ()
            self .hide ()
            self .tray_icon .show ()
        else :
            e .accept ()
            self .force_quit ()

    def open_notebook (self ):
        try :
            notepad_path =os .path .join ("notepad","eDiary.exe")
            notepad_path =os .path .abspath (notepad_path )
            if sys .platform .startswith ("win"):
                os .startfile (notepad_path )
            else :
                subprocess .Popen ([notepad_path ])
        except Exception as e :
            QMessageBox .warning (self ,"错误",f"运行失败: {e}")

    def toggle_batch_mode (self ):
        is_active =not self .tool_grid .show_select_box 
        self .tool_grid .enable_batch_mode (is_active )
        if is_active :
            self .btn_batch .setText ("退出批量")
            self .btn_run_batch .show ()
        else :
            self .btn_batch .setText ("批量模式")
            self .btn_run_batch .hide ()

    def do_batch_run (self ):
        selected =self .tool_grid .get_selected_tools ()
        if not selected :
            QMessageBox .information (self ,"提示","未选择任何工具")
            return 

        self .run_tools_batch (selected )

        self .toggle_batch_mode ()

    def check_tools_health (self ):
        try :
            self ._health_status =self .health_checker .check_all (self .tools )
            missing =self .health_checker .get_missing_tools (self .tools )
            if missing :
                names =[t .get ("name","")for t in missing [:5 ]]
                logger .info (f"工具健康检查: {len(missing)} 个工具路径缺失 ({', '.join(names)}...)")
            self .update_tool_grid ()
        except Exception as e :
            logger .warning (f"工具健康检查失败: {e}")

    def load_main_window_state_and_geometry (self ):
        geo_bytes =load_main_window_geometry ()
        state_bytes =load_main_window_state ()
        if geo_bytes :
            self .restoreGeometry (QByteArray (geo_bytes ))
        if state_bytes :
            self .restoreState (QByteArray (state_bytes ))
        self ._clamp_to_screen ()

def main ():
    QApplication .setHighDpiScaleFactorRoundingPolicy (
        Qt .HighDpiScaleFactorRoundingPolicy .PassThrough
    )
    os .environ ["QT_ENABLE_HIGHDPI_SCALING"]="1"
    os .environ ["QT_SCALE_FACTOR_ROUNDING_POLICY"]="PassThrough"

    install_log_hooks ()
    _file .stream .write ("\n")
    _file .stream .flush ()
    app =QApplication (sys .argv )
    w =MainWindow ()
    w .show ()
    sys .exit (app .exec ())

if __name__ =="__main__":
    main ()
