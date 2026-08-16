import sys
import os

from PyQt6 .QtWidgets import (
QFrame ,QVBoxLayout ,QHBoxLayout ,QLabel ,QLineEdit ,QPushButton ,
QComboBox ,QScrollArea ,QWidget ,QToolButton ,QMenu ,QDialog ,
QFileDialog ,QMessageBox ,QInputDialog ,QCheckBox ,QGridLayout ,QSizePolicy ,
QTabWidget ,QStackedWidget ,QSplitter ,QTableWidget ,QTableWidgetItem ,
QHeaderView ,QAbstractItemView
)
from PyQt6 .QtCore import Qt ,pyqtSignal ,QTimer ,QEvent ,QSettings ,QVariantAnimation ,QEasingCurve
from PyQt6 .QtGui import QAction ,QKeySequence ,QIcon ,QColor ,QPalette


from config import (
SETTINGS ,TOOL_TYPES ,THEME ,save_settings ,load_settings ,
save_categories ,save_tools ,DEFAULT_CATEGORIES ,
)
from utils import (
fuzzy_search ,is_tool_favorited ,add_favorite_tool ,remove_favorite_tool ,
)

FORBIDDEN_CATEGORIES =["","最近启动","我的收藏","全部工具"]
FORBIDDEN_HOTKEYS ={
'ctrl+c','ctrl+v','ctrl+x','ctrl+z','ctrl+y','ctrl+f'
}


class _AnimatedMenuItem (QWidget ):
    def __init__ (self ,text ,danger =False ,parent =None ):
        super ().__init__ (parent )
        self ._danger =danger 
        self ._t =0.0 
        self ._label =QLabel (text ,self )
        self ._label .setAlignment (Qt .AlignmentFlag .AlignVCenter |Qt .AlignmentFlag .AlignLeft )
        lay =QHBoxLayout (self )
        lay .setContentsMargins (12 ,7 ,12 ,7 )
        lay .setSpacing (8 )
        lay .addWidget (self ._label )
        self .setCursor (Qt .CursorShape .PointingHandCursor )

        self ._anim =QVariantAnimation (self )
        self ._anim .setDuration (140 )
        self ._anim .setEasingCurve (QEasingCurve .Type .OutCubic )

        def _on_val (v ):
            self ._t =float (v )
            self ._apply_style ()

        self ._anim .valueChanged .connect (_on_val )
        self ._apply_style ()

    def _theme (self ):
        try :
            return THEME or {}
        except Exception :
            return {}

    def _apply_style (self ):
        theme =self ._theme ()
        base =QColor (theme .get ('dropdown','rgba(25,25,32,0.96)'))
        hover =QColor (theme .get ('hover','rgba(255,255,255,0.10)'))
        text =QColor (theme .get ('text','#E7E7F2'))
        primary =QColor (theme .get ('primary','#7C5CFF'))
        danger =QColor (255 ,90 ,110 )

        a =int (18 +55 *self ._t )
        bg =QColor (hover )
        bg .setAlpha (a )
        fg =danger if self ._danger else text 
        if self ._t >0.001 and not self ._danger :
            try :
                fg =QColor (primary )
            except Exception :
                pass 

        self .setStyleSheet (
        "QWidget {"
        f"background-color: rgba({bg .red ()},{bg .green ()},{bg .blue ()},{bg .alpha ()});"
        "border-radius: 10px;"
        "}"
        )
        self ._label .setStyleSheet (
        "QLabel {"
        f"color: rgba({fg .red ()},{fg .green ()},{fg .blue ()},{fg .alpha ()});"
        "font-size: 12px;"
        "}"
        )

    def enterEvent (self ,e ):
        try :
            self ._anim .stop ()
        except Exception :
            pass 
        self ._anim .setStartValue (self ._t )
        self ._anim .setEndValue (1.0 )
        self ._anim .start ()
        super ().enterEvent (e )

    def leaveEvent (self ,e ):
        try :
            self ._anim .stop ()
        except Exception :
            pass 
        self ._anim .setStartValue (self ._t )
        self ._anim .setEndValue (0.0 )
        self ._anim .start ()
        super ().leaveEvent (e )


def _animate_menu_show (menu :QMenu ):
    try :
        menu .setWindowOpacity (0.0 )
    except Exception :
        return 

    anim =QVariantAnimation (menu )
    anim .setDuration (140 )
    anim .setEasingCurve (QEasingCurve .Type .OutCubic )
    base_pos =menu .pos ()
    lift =6 

    def _on (v ):
        t =float (v )
        try :
            menu .setWindowOpacity (t )
        except Exception :
            pass 
        try :
            menu .move (base_pos .x (),base_pos .y ()+int (lift *(1.0 -t )))
        except Exception :
            pass 

    anim .valueChanged .connect (_on )

    def _start ():
        try :
            nonlocal base_pos 
            base_pos =menu .pos ()
        except Exception :
            pass 
        anim .setStartValue (0.0 )
        anim .setEndValue (1.0 )
        anim .start ()

    QTimer .singleShot (0 ,_start )


def _add_animated_action (menu :QMenu ,text :str ,trigger_fn ,danger =False ):
    act =QAction (text ,menu )
    if trigger_fn is not None :
        act .triggered .connect (trigger_fn )
    try :
        from PyQt6 .QtWidgets import QWidgetAction 
        wa =QWidgetAction (menu )
        w =_AnimatedMenuItem (text ,danger =danger ,parent =menu )
        wa .setDefaultWidget (w )
        wa .triggered .connect (act .trigger )
        menu .addAction (wa )
        return wa 
    except Exception :
        menu .addAction (act )
        return act 


if sys .platform .startswith ('win'):
    CREATE_NEW_CONSOLE =0x00000010 
else :
    CREATE_NEW_CONSOLE =0 


class TitleBar (QWidget ):
    def __init__ (self ,parent =None ,show_minmax =True ):
        super ().__init__ (parent )
        self .parent =parent 
        self .setObjectName ("titleBar")
        self .show_minmax =show_minmax 
        self .init_ui ()

    def init_ui (self ):
        lay =QHBoxLayout (self )
        lay .setContentsMargins (0 ,0 ,0 ,0 )
        lay .setSpacing (5 )

        self .title_label =QLabel ("天狐渗透工具箱-社区版V4.0",self )
        self .title_label .setStyleSheet ("font-size:16px; font-weight:bold; padding-left:10px;")
        lay .addWidget (self .title_label )

        lay .addStretch ()

        # 顶部性能监控文字已停用
        self .perf_label =QLabel ("",self )
        self .perf_label .hide ()
        # self .perf_label .setAlignment (Qt .AlignmentFlag .AlignVCenter |Qt .AlignmentFlag .AlignRight )
        # self .perf_label .setStyleSheet ("font-size:12px; padding-right:10px;")
        # self .perf_label .setMinimumWidth (180 )
        # lay .addWidget (self .perf_label )

        self .btn_min =QPushButton ("🗕")
        self .btn_min .setObjectName ("titleButton")
        self .btn_min .clicked .connect (self .parent .showMinimized )

        self .btn_max =QPushButton ("🗖")
        self .btn_max .setObjectName ("titleButton")
        self .btn_max .clicked .connect (self .toggle_maximize )

        self .btn_close =QPushButton ("✕")
        self .btn_close .setObjectName ("titleButton")
        self .btn_close .clicked .connect (self .handle_close )

        lay .addWidget (self .btn_min )
        lay .addWidget (self .btn_max )
        lay .addWidget (self .btn_close )

        if not self .show_minmax :
            self .btn_min .hide ()
            self .btn_max .hide ()

        self .setFixedHeight (60 )
        self .dragging =False 
        self .drag_position =None 

    def toggle_maximize (self ):
        if self .parent .isMaximized ():
            self .parent .showNormal ()
            self .btn_max .setText ("🗖")
        else :
            self .parent .showMaximized ()
            self .btn_max .setText ("🗗")

    def handle_close (self ):
        self .parent .close ()

    def mousePressEvent (self ,e ):
        if e .button ()==Qt .MouseButton .LeftButton :
            self .dragging =True 
            self .drag_position =e .globalPosition ().toPoint ()-self .parent .pos ()

    def mouseMoveEvent (self ,e ):
        if self .dragging and not self .parent .isMaximized ():
            self .parent .move (e .globalPosition ().toPoint ()-self .drag_position )

    def mouseReleaseEvent (self ,e ):
        self .dragging =False 

    def mouseDoubleClickEvent (self ,e ):
        if e .button ()==Qt .MouseButton .LeftButton :
            self .toggle_maximize ()


class SearchBar (QFrame ):
    search_changed =pyqtSignal (str )

    def __init__ (self ,parent =None ):
        super ().__init__ (parent )
        self .init_ui ()
        self .search_timer =QTimer ()
        self .search_timer .setSingleShot (True )
        self .search_timer .timeout .connect (self .emit_search )

    def init_ui (self ):
        lay =QHBoxLayout (self )
        lay .setContentsMargins (0 ,0 ,0 ,0 )
        lay .setSpacing (6 )

        # lab_icon =QLabel ("",self )  # 已移除左侧空占位，搜索框与卡片左侧对齐
        # lay .addWidget (lab_icon )

        self .search_input =QLineEdit ()
        self .search_input .setPlaceholderText ("搜索工具...")
        self .search_input .textChanged .connect (self .on_text_changed )
        lay .addWidget (self .search_input )

    def on_text_changed (self ,text ):
        self .search_timer .stop ()
        self .search_timer .start (300 )

    def emit_search (self ):
        self .search_changed .emit (self .search_input .text ())


class CategoryButton (QPushButton ):
    def __init__ (self ,text ,panel ,is_user_category =True ,category_key =None ):
        super ().__init__ (text )
        self .panel =panel 
        self .setObjectName ("categoryBtn")
        self .setCheckable (True )
        self .setContextMenuPolicy (Qt .ContextMenuPolicy .CustomContextMenu )
        self .customContextMenuRequested .connect (self .show_menu )
        self .is_user_category =is_user_category 
        self .category_key =category_key 
        self .setCursor (Qt .CursorShape .PointingHandCursor )

    def show_menu (self ,pos ):
        menu =QMenu (self )
        _add_animated_action (menu ,"新建分类",self .add_cat )

        try :
            menu .aboutToShow .connect (lambda :_animate_menu_show (menu ))
        except Exception :
            pass 

        if self .category_key not in ("我的收藏","最近启动")and self .category_key !="":
            menu .addSeparator ()
            act_rename =_add_animated_action (menu ,"重命名",self .rename_cat )
            act_del =_add_animated_action (menu ,"删除",self .del_cat ,danger =True )
            menu .addSeparator ()
            _add_animated_action (menu ,"上移",self .move_up )
            _add_animated_action (menu ,"下移",self .move_down )

        menu .exec (self .mapToGlobal (pos ))

    def add_cat (self ):
        if hasattr (self .panel ,"category_added"):
            self .panel .category_added .emit ("")

    def rename_cat (self ):
        old_key =self .category_key 
        diag =QInputDialog (self )
        diag .setWindowTitle ("重命名分类")
        diag .setLabelText ("新的分类名称:")
        diag .setTextValue (old_key )
        if diag .exec ()==QDialog .DialogCode .Accepted :
            newval =diag .textValue ().strip ()
            if newval and newval !=old_key :
                if hasattr (self .panel ,"category_renamed"):
                    self .panel .category_renamed .emit (old_key ,newval )

    def del_cat (self ):
        cat_to_del =self .category_key 
        if hasattr (self .panel ,"category_deleted"):
            self .panel .category_deleted .emit (cat_to_del )

    def move_up (self ):
        if hasattr (self .panel ,"category_move"):
            self .panel .category_move .emit (self .category_key ,-1 )

    def move_down (self ):
        if hasattr (self .panel ,"category_move"):
            self .panel .category_move .emit (self .category_key ,1 )


class CategoryPanel (QFrame ):
    category_selected =pyqtSignal (str )
    category_renamed =pyqtSignal (str ,str )
    category_deleted =pyqtSignal (str )
    category_added =pyqtSignal (str )
    category_move =pyqtSignal (str ,int )

    def __init__ (self ,categories ,parent =None ):
        super ().__init__ (parent )
        self .categories =categories 
        self .current_button =None 
        self .buttons ={}
        self .extra_btns ={}
        self .init_ui ()

    def init_ui (self ):
        self .setContextMenuPolicy (Qt .ContextMenuPolicy .CustomContextMenu )
        self .customContextMenuRequested .connect (self .show_panel_menu )

        lay =QVBoxLayout (self )
        lay .setContentsMargins (0 ,0 ,0 ,0 )
        lay .setSpacing (0 )

        self .scroll =QScrollArea ()
        self .scroll .setWidgetResizable (True )
        self .scroll .setHorizontalScrollBarPolicy (Qt .ScrollBarPolicy .ScrollBarAlwaysOff )

        self .container =QWidget ()
        self .container .setObjectName ("categoryContainer")
        self .container_layout =QVBoxLayout (self .container )
        self .container_layout .setContentsMargins (0 ,0 ,0 ,0 )
        self .container_layout .setSpacing (10 )

        all_btn =CategoryButton ("全部工具",self ,is_user_category =False ,category_key ="")
        all_btn .clicked .connect (lambda :self .on_click (all_btn ,""))
        all_btn .setChecked (True )
        self .buttons [""]=all_btn 
        self .container_layout .addWidget (self ._wrap_cat_row (all_btn ))

        self .update_categories (self .categories )

        self .container_layout .addStretch ()
        self .scroll .setWidget (self .container )
        lay .addWidget (self .scroll )
        self .setLayout (lay )

    def show_panel_menu (self ,pos ):
        menu =QMenu (self )
        _add_animated_action (menu ,"新建分类",lambda :self .category_added .emit (""))

        try :
            menu .aboutToShow .connect (lambda :_animate_menu_show (menu ))
        except Exception :
            pass 

        menu .exec (self .mapToGlobal (pos ))

    def _wrap_cat_row (self ,btn ,extra_btn =None ):
        row =QWidget ()
        hl =QHBoxLayout (row )
        hl .setContentsMargins (0 ,0 ,0 ,0 )
        hl .setSpacing (0 )
        hl .addWidget (btn )
        if extra_btn :
            hl .addStretch ()
            hl .addWidget (extra_btn )
        return row 

    def update_categories (self ,categories ,category_counts =None ):
        if category_counts is None :
            category_counts ={}

        current_cat =""
        if hasattr (self ,'current_button')and self .current_button :
            raw_text =self .current_button .text ()
            for _ic in ("📁 ","🕘 ","⭐ ","🗒 "):
                raw_text =raw_text .replace (_ic ,"")
            idx =raw_text .rfind ("(")
            if idx !=-1 :
                raw_text =raw_text [:idx ].strip ()
            if raw_text =="全部工具":
                current_cat =""
            else :
                current_cat =raw_text 

        for c ,btn in list (self .buttons .items ()):
            if c !="":
                widget =btn .parentWidget ()
                self .container_layout .removeWidget (widget )
                widget .deleteLater ()
                del self .buttons [c ]
        self .extra_btns .clear ()

        ordered =[]
        if "最近启动"in categories :
            ordered .append ("最近启动")
        if "我的收藏"in categories :
            ordered .append ("我的收藏")
        ordered +=[cat for cat in categories if cat not in ("我的收藏","最近启动")and cat ]

        for cat in ordered :
            cc =category_counts .get (cat ,0 )
            if cat =="最近启动":
                icon ="🕘"
            elif cat =="我的收藏":
                icon ="⭐"
            else :
                icon ="📁"
            text =f"{icon} {cat}"
            if cc >0 :
                text +=f" ({cc})"
            is_user_cat =(cat not in DEFAULT_CATEGORIES or cat in ("我的收藏","最近启动"))
            cb =CategoryButton (
            text ,self ,is_user_category =is_user_cat ,category_key =cat 
            )
            cb .clicked .connect (lambda _ ,b =cb ,n =cat :self .on_click (b ,n ))
            self .buttons [cat ]=cb 
            self .container_layout .insertWidget (
            self .container_layout .count ()-1 ,
            self ._wrap_cat_row (cb )
            )

        all_count =category_counts .get ("",None )
        if all_count is not None :
            self .buttons [""].setText (f"全部工具 ({all_count})")
        else :
            self .buttons [""].setText ("全部工具")

        if current_cat in self .buttons :
            self .on_click (self .buttons [current_cat ],current_cat )
        else :
            self .on_click (self .buttons [""],"")

    def on_click (self ,btn ,cat ):
        for b in self .buttons .values ():
            if b !=btn :
                b .setChecked (False )
        btn .setChecked (True )
        self .current_button =btn 
        self .category_selected .emit (cat )

class ToolDialog (QDialog ):
    def __init__ (self ,categories ,tool_data =None ,parent =None ):
        super ().__init__ (parent )
        self .categories =categories 
        self .tool_data =tool_data 
        # self.shortcut_key = ""  # 已禁用全局热键功能
        self .init_ui ()
        self .setModal (True )

    def init_ui (self ):
        self .setWindowFlag (Qt .WindowType .FramelessWindowHint )
        self .setObjectName ("toolDialog")
        main_lay =QVBoxLayout (self )
        main_lay .setContentsMargins (0 ,0 ,0 ,0 )
        main_lay .setSpacing (0 )

        self .title_bar =TitleBar (self ,show_minmax =False )
        if not self .tool_data :
            self .title_bar .title_label .setText ("添加工具")
        else :
            self .title_bar .title_label .setText ("编辑工具")
        try :
            self .title_bar .perf_label .hide ()
        except Exception :
            pass 
        main_lay .addWidget (self .title_bar )

        content =QWidget ()
        try :

            if SETTINGS .get ("theme")=="red_blue_glass":
                content .setStyleSheet ("background: transparent;")
        except Exception :
            pass 
        lay =QVBoxLayout (content )
        lay .setSpacing (10 )
        lay .setContentsMargins (10 ,10 ,10 ,10 )

        lb_name =QLabel ("工具名称:")
        lay .addWidget (lb_name )
        self .ed_name =QLineEdit ()
        if self .tool_data :
            self .ed_name .setText (self .tool_data ['name'])
        lay .addWidget (self .ed_name )

        lb_type =QLabel ("工具类型:")
        lay .addWidget (lb_type )
        self .cb_type =QComboBox ()
        self .refresh_type_choices ()
        if self .tool_data :
            self .cb_type .setCurrentText (self .tool_data ['type'])
        self .cb_type .currentTextChanged .connect (self .on_type_changed )
        lay .addWidget (self .cb_type )

        lb_path =QLabel ("工具路径:")
        lay .addWidget (lb_path )
        hpath =QHBoxLayout ()
        self .ed_path =QLineEdit ()
        if self .tool_data :
            self .ed_path .setText (self .tool_data .get ("path",""))
        hpath .addWidget (self .ed_path )
        self .btn_browse =QPushButton ("浏览")
        self .btn_browse .setObjectName ("noHoverBtn")
        self .btn_browse .clicked .connect (self .browse_file )
        hpath .addWidget (self .btn_browse )
        lay .addLayout (hpath )

        self .lb_url =QLabel ("网页地址:")
        lay .addWidget (self .lb_url )
        self .ed_url =QLineEdit ()
        if self .tool_data :
            self .ed_url .setText (self .tool_data .get ("url",""))
        lay .addWidget (self .ed_url )
        self .lb_url .hide ()
        self .ed_url .hide ()

        lb_cat =QLabel ("工具分类:")
        lay .addWidget (lb_cat )
        self .cb_cat =QComboBox ()
        self .cb_cat .setEditable (True )
        filtered_categories =[cat for cat in self .categories if cat not in ("最近启动","我的收藏")]
        self .cb_cat .addItems (sorted (filtered_categories ))
        if self .tool_data :
            self .cb_cat .setCurrentText (self .tool_data ['category'])
        lay .addWidget (self .cb_cat )

        lb_params =QLabel ("启动参数:")
        lay .addWidget (lb_params )
        self .ed_params =QLineEdit ()
        if self .tool_data :
            self .ed_params .setText (self .tool_data .get ("params",""))
        lay .addWidget (self .ed_params )

        lb_desc =QLabel ("工具描述:")
        lay .addWidget (lb_desc )
        self .ed_desc =QLineEdit ()
        if self .tool_data :
            self .ed_desc .setText (self .tool_data .get ("description",""))
        lay .addWidget (self .ed_desc )

        # lb_tags =QLabel ("标签 (最多3个, 每个≤10字符, 英文逗号分隔):")  # 标签功能已禁用
        # lay .addWidget (lb_tags )
        # self .ed_tags =QLineEdit ()
        # self .ed_tags .setPlaceholderText ("如：内网, 提权, webshell")
        # if self .tool_data and self .tool_data .get ("tags"):
        #     self .ed_tags .setText (", ".join (self .tool_data .get ("tags",[])[:3 ]))
        # lay .addWidget (self .ed_tags )
        # lab_tip =QLabel ("多个标签请用英文逗号 , 分隔；每个标签最多10字符，最多3个标签")
        # lab_tip .setStyleSheet ("color: #888; font-size: 11px; padding-left:3px;")
        # lay .addWidget (lab_tip )

        lb_weight =QLabel ("显示权重(任意数字):")
        lay .addWidget (lb_weight )
        self .ed_weight =QLineEdit ()
        self .ed_weight .setPlaceholderText ("如 5、3.14、-2.5，数字越大越靠前")
        if self .tool_data :
            w =self .tool_data .get ("weight",None )
            if w is not None :
                self .ed_weight .setText (str (w ))
            else :
                self .ed_weight .setText ("0")
        else :
            self .ed_weight .setText ("0")
        lay .addWidget (self .ed_weight )

        # lb_short = QLabel("快捷键:")  # 已禁用全局热键功能
        # lay.addWidget(lb_short)
        # hshort = QHBoxLayout()
        # self.ed_shortcut = QLineEdit()
        # self.ed_shortcut.setPlaceholderText("按下组合键或手动输入")
        # if self.tool_data and hasattr(self.parent(), "tool_shortcuts"):
        #     exist = self.parent().tool_shortcuts.get(self.tool_data['name'], "")
        #     if exist:
        #         self.ed_shortcut.setText(exist)
        #         self.shortcut_key = exist
        # btn_clear = QPushButton("清除")
        # btn_clear.setObjectName("noHoverBtn")
        # btn_clear.clicked.connect(self.clear_short)
        # hshort.addWidget(self.ed_shortcut)
        # hshort.addWidget(btn_clear)
        # lay.addLayout(hshort)

        hbtn =QHBoxLayout ()
        self .btn_save =QPushButton ("保存")
        self .btn_save .setObjectName ("noHoverBtn")
        self .btn_save .clicked .connect (self ._on_save_clicked )
        self .btn_cancel =QPushButton ("取消")
        self .btn_cancel .setObjectName ("noHoverBtn")
        self .btn_cancel .clicked .connect (self .reject )
        hbtn .addWidget (self .btn_save )
        hbtn .addWidget (self .btn_cancel )
        lay .addLayout (hbtn )

        main_lay .addWidget (content )
        self .setMinimumWidth (500 )

        self .on_type_changed (self .cb_type .currentText ())

    def refresh_type_choices (self ):
        self .cb_type .clear ()
        base =list (TOOL_TYPES )

        try :
            cli_py =SETTINGS .get ("cli_python_interpreters",[])or []
            cli_java =SETTINGS .get ("cli_java_interpreters",[])or []

            py_names =[]
            for item in cli_py :
                if not isinstance (item ,dict ):
                    continue 
                nm =str (item .get ("name","")).strip ()
                p =str (item .get ("path","")).strip ()
                if nm and p :
                    py_names .append (nm )

            java_names =[]
            for item in cli_java :
                if not isinstance (item ,dict ):
                    continue 
                nm =str (item .get ("name","")).strip ()
                p =str (item .get ("path","")).strip ()
                if nm and p :
                    java_names .append (nm )

            py_names =sorted (set (py_names ))
            java_names =sorted (set (java_names ))

            extra =[f"Python({nm})"for nm in py_names ]+[f"Java({nm})"for nm in java_names ]
            self .cb_type .addItems (base +extra )
        except Exception :
            self .cb_type .addItems (base )

    def on_type_changed (self ,t ):
        is_web =(t =="网页")
        self .lb_url .setVisible (is_web )
        self .ed_url .setVisible (is_web )
        self .ed_path .setVisible (not is_web )
        self .btn_browse .setVisible (not is_web )
        self .ed_params .setVisible (not is_web )

    def browse_file (self ):
        current_path =self .ed_path .text ().strip ()
        start_dir =""
        if current_path :
            start_dir =os .path .dirname (current_path )
            if not os .path .isabs (start_dir ):
                start_dir =""
        fi ,_ =QFileDialog .getOpenFileName (self ,"选择工具文件",start_dir )
        if fi :
            self .ed_path .setText (fi )

    # def clear_short(self):  # 已禁用全局热键功能
    #     self.ed_shortcut.clear()
    #     self.shortcut_key = ""
    #     if self.tool_data and hasattr(self.parent(), "tool_shortcuts"):
    #         nm = self.tool_data['name']
    #         if nm in self.parent().tool_shortcuts:
    #             del self.parent().tool_shortcuts[nm]
    #             sets = QSettings("config/shortcuts.ini", QSettings.Format.IniFormat)
    #             sets.remove(f"shortcuts/{nm}")
    #             sets.sync()
    #             # self.parent().init_shortcuts()

    # def keyPressEvent(self, e):  # 已禁用全局热键功能
    #     if self.ed_shortcut.hasFocus():
    #         mods = []
    #         if e.modifiers() & Qt.KeyboardModifier.ControlModifier:
    #             mods.append("Ctrl")
    #         if e.modifiers() & Qt.KeyboardModifier.AltModifier:
    #             mods.append("Alt")
    #         if e.modifiers() & Qt.KeyboardModifier.ShiftModifier:
    #             mods.append("Shift")
    #         if e.key() in (Qt.Key.Key_Control, Qt.Key.Key_Alt, Qt.Key.Key_Shift):
    #             return
    #         keystr = QKeySequence(e.key()).toString()
    #         if not keystr:
    #             return
    #         final = "+".join(mods + [keystr])
    #         forbidden = final.strip().lower().replace(' ', '')
    #         if forbidden in FORBIDDEN_HOTKEYS:
    #             QMessageBox.warning(self, "快捷键冲突", "此快捷键为系统常用快捷键，禁止使用")
    #             self.ed_shortcut.clear()
    #             return
    #         if self.check_conflict(final):
    #             QMessageBox.warning(self, "快捷键冲突", "此快捷键已被其它工具占用")
    #             self.ed_shortcut.clear()
    #             return
    #         self.ed_shortcut.setText(final)
    #         self.shortcut_key = final
    #         if self.tool_data:
    #             sets = QSettings("config/shortcuts.ini", QSettings.Format.IniFormat)
    #             sets.setValue(f"shortcuts/{self.tool_data['name']}", final)
    #             sets.sync()
    #             if hasattr(self.parent(), "tool_shortcuts"):
    #                 self.parent().tool_shortcuts[self.tool_data['name']] = final
    #                     # self.parent().init_shortcuts()
    #     else:
    #         super().keyPressEvent(e)

    # def check_conflict(self, newval):  # 已禁用全局热键功能
    #     if not hasattr(self.parent(), "tool_shortcuts"):
    #         return False
    #     curr = self.tool_data['name'] if self.tool_data else None
    #     for nm, val in self.parent().tool_shortcuts.items():
    #         if val == newval and nm != curr:
    #             return True
    #     return False

    def _on_save_clicked (self ):
        # tags_str =self .ed_tags .text ().strip ()  # 标签功能已禁用
        # tags =[t .strip ()for t in tags_str .split (",")if t .strip ()]
        # if len (tags )>3 :
        #     QMessageBox .warning (self ,"标签数量超限","最多只能填写3个标签！")
        #     return 
        # long_tags =[t for t in tags if len (t )>10 ]
        # if long_tags :
        #     QMessageBox .warning (self ,"标签超长","每个标签最多10个字符！")
        #     return 
        # val = self.ed_shortcut.text().strip()  # 已禁用全局热键功能
        # forbidden = val.lower().replace(' ', '')
        # if forbidden and forbidden in FORBIDDEN_HOTKEYS:
        #     QMessageBox.warning(self, "快捷键冲突", "此快捷键为系统常用快捷键，禁止使用")
        #     return
        # if val and self.check_conflict(val):
        #     QMessageBox.warning(self, "快捷键冲突", "此快捷键已被其它工具占用")
        #     return
        self .accept ()

    def get_tool_data (self ):
        data ={}
        data ['name']=self .ed_name .text ().strip ()
        data ['category']=self .cb_cat .currentText ().strip ()
        data ['type']=self .cb_type .currentText ()

        data ['description']=self .ed_desc .text ().strip ()
        try :
            data ['weight']=float (self .ed_weight .text ().strip ())
        except Exception :
            data ['weight']=0.0

        # tags_str =self .ed_tags .text ().strip ()  # 标签功能已禁用
        # tags =[t .strip ()for t in tags_str .split (",")if t .strip ()]
        # tags =tags [:3 ]
        # tags =[t [:10 ]for t in tags ]
        # data ['tags']=tags 
        data ['tags']=[]  # 标签功能已禁用 

        if data ['type']=="网页":
            data ['url']=self .ed_url .text ().strip ()
            data ['path']=""
            data ['params']=""
        else :
            data ['path']=self .ed_path .text ().strip ()
            data ['params']=self .ed_params .text ().strip ()
            data ['url']=""

        data ['custom_interpreter_name']=""
        data ['custom_interpreter_type']=""

        try :
            tt =str (data .get ('type','')or '')
            if tt .startswith ("Python(")and tt .endswith (")"):
                data ['custom_interpreter_type']="python"
                data ['custom_interpreter_name']=tt [7 :-1 ]
            elif tt .startswith ("Java(")and tt .endswith (")"):
                data ['custom_interpreter_type']="java"
                data ['custom_interpreter_name']=tt [5 :-1 ]
        except Exception :
            pass 

        # if hasattr(self.parent(), "tool_shortcuts"):  # 已禁用全局热键功能
        #     if self.tool_data and self.tool_data['name'] in self.parent().tool_shortcuts:
        #         if (not self.shortcut_key) or (self.tool_data['name'] != data['name']):
        #             if self.tool_data['name'] in self.parent().tool_shortcuts:
        #                 del self.parent().tool_shortcuts[self.tool_data['name']]
        #                 # self.parent().init_shortcuts()
        #     if self.shortcut_key:
        #         self.parent().tool_shortcuts[data['name']] = self.shortcut_key

        return data 

class SettingsDialog (QDialog ):
    settings_changed =pyqtSignal (dict )

    def __init__ (self ,parent =None ):
        super ().__init__ (parent )
        self .init_ui ()

    def init_ui (self ):
        self .setWindowFlag (Qt .WindowType .FramelessWindowHint )
        self .setObjectName ("settingsDialog")
        ml =QVBoxLayout (self )
        ml .setContentsMargins (0 ,0 ,0 ,0 )
        ml .setSpacing (0 )

        self .title_bar =TitleBar (self ,show_minmax =False )
        self .title_bar .title_label .setText ("设置")
        try :
            self .title_bar .perf_label .hide ()
        except Exception :
            pass
        ml .addWidget (self .title_bar )

        content =QWidget ()
        try :
            if SETTINGS .get ("theme")=="red_blue_glass":
                content .setStyleSheet ("background: transparent;")
        except Exception :
            pass
        outer_lay =QVBoxLayout (content )
        outer_lay .setContentsMargins (10 ,10 ,10 ,10 )
        outer_lay .setSpacing (10 )

        self .tab_widget =QTabWidget ()
        self .tab_widget .setObjectName ("settingsTabWidget")

        self ._build_general_tab ()
        self ._build_env_tab ()
        self ._build_advanced_tab ()

        outer_lay .addWidget (self .tab_widget )

        hb_btn =QHBoxLayout ()
        hb_btn .addStretch ()
        btn_save =QPushButton ("保存")
        btn_save .setObjectName ("noHoverBtn")
        btn_save .clicked .connect (self .save_settings )
        btn_cancel =QPushButton ("取消")
        btn_cancel .setObjectName ("noHoverBtn")
        btn_cancel .clicked .connect (self .reject )
        hb_btn .addWidget (btn_save )
        hb_btn .addWidget (btn_cancel )
        outer_lay .addLayout (hb_btn )

        ml .addWidget (content )
        self .setLayout (ml )
        self .setMinimumSize (560 ,480 )
        self .resize (560 ,560 )

    def _build_general_tab (self ):
        tab =QWidget ()
        lay =QVBoxLayout (tab )
        lay .setSpacing (12 )
        lay .setContentsMargins (10 ,10 ,10 ,10 )

        lay .addWidget (QLabel (""))
        health_row =QHBoxLayout ()
        health_row .addWidget (QLabel ("工具健康检查:"))
        btn_health =QPushButton ("立即检查")
        btn_health .setObjectName ("noHoverBtn")
        btn_health .clicked .connect (self ._on_health_check )
        health_row .addWidget (btn_health )
        self ._health_result_label =QLabel ("")
        self ._health_result_label .setStyleSheet ("color: #aaa; font-size: 11px;")
        health_row .addWidget (self ._health_result_label )
        health_row .addStretch ()
        lay .addLayout (health_row )

        lay .addWidget (QLabel ("数据管理:"))
        data_row =QHBoxLayout ()
        btn_import =QPushButton ("导入")
        btn_import .setObjectName ("noHoverBtn")
        btn_import .clicked .connect (self ._on_import_data )
        data_row .addWidget (btn_import )
        btn_export =QPushButton ("导出")
        btn_export .setObjectName ("noHoverBtn")
        btn_export .clicked .connect (self ._on_export_data )
        data_row .addWidget (btn_export )
        data_row .addStretch ()
        lay .addLayout (data_row )

        lay .addStretch ()
        self .tab_widget .addTab (tab ,"常规")

    def _on_import_data (self ):
        parent =self .parent ()
        if parent and hasattr (parent ,"import_data"):
            parent .import_data ()

    def _on_export_data (self ):
        parent =self .parent ()
        if parent and hasattr (parent ,"export_data"):
            parent .export_data ()

    def _build_env_tab (self ):
        tab =QWidget ()
        scroll =QScrollArea ()
        scroll .setWidgetResizable (True )
        scroll_w =QWidget ()
        lay =QVBoxLayout (scroll_w )
        lay .setSpacing (12 )
        lay .setContentsMargins (10 ,10 ,10 ,10 )

        lay .addWidget (QLabel ("自定义Python路径(可选):"))
        hpy =QHBoxLayout ()
        self .ed_py =QLineEdit (SETTINGS .get ("python_path",""))
        hpy .addWidget (self .ed_py )
        btn_browse_py =QPushButton ("浏览")
        btn_browse_py .setObjectName ("noHoverBtn")
        btn_browse_py .clicked .connect (self .browse_py )
        hpy .addWidget (btn_browse_py )
        lay .addLayout (hpy )

        lay .addWidget (QLabel ("Java 8路径(可选):"))
        hj8 =QHBoxLayout ()
        self .ed_j8 =QLineEdit (SETTINGS .get ("java8_path","Java_path/Java_8_win/bin"))
        hj8 .addWidget (self .ed_j8 )
        btn_j8 =QPushButton ("浏览")
        btn_j8 .setObjectName ("noHoverBtn")
        btn_j8 .clicked .connect (lambda :self .browse_dir (self .ed_j8 ))
        hj8 .addWidget (btn_j8 )
        lay .addLayout (hj8 )

        lay .addWidget (QLabel ("Java 11路径(可选):"))
        hj11 =QHBoxLayout ()
        self .ed_j11 =QLineEdit (SETTINGS .get ("java11_path","Java_path/Java_11_win/bin"))
        hj11 .addWidget (self .ed_j11 )
        btn_j11 =QPushButton ("浏览")
        btn_j11 .setObjectName ("noHoverBtn")
        btn_j11 .clicked .connect (lambda :self .browse_dir (self .ed_j11 ))
        hj11 .addWidget (btn_j11 )
        lay .addLayout (hj11 )

        lay .addStretch ()
        scroll .setWidget (scroll_w )
        self ._fix_scroll_viewport (scroll ,scroll_w )

        tab_lay =QVBoxLayout (tab )
        tab_lay .setContentsMargins (0 ,0 ,0 ,0 )
        tab_lay .addWidget (scroll )
        self .tab_widget .addTab (tab ,"环境")

    def _build_advanced_tab (self ):
        tab =QWidget ()
        scroll =QScrollArea ()
        scroll .setWidgetResizable (True )
        scroll_w =QWidget ()
        lay =QVBoxLayout (scroll_w )
        lay .setSpacing (12 )
        lay .setContentsMargins (10 ,10 ,10 ,10 )

        self .cli_python_list =list (SETTINGS .get ("cli_python_interpreters",[])or [])
        self .cli_java_list =list (SETTINGS .get ("cli_java_interpreters",[])or [])

        lay .addWidget (QLabel ("Python解释器:"))
        self .table_py =self ._make_interpreter_table ()
        lay .addWidget (self .table_py )
        py_btn_row =QHBoxLayout ()
        btn_add_cli_py =QPushButton ("新增")
        btn_add_cli_py .setObjectName ("noHoverBtn")
        btn_add_cli_py .clicked .connect (self .add_cli_python )
        py_btn_row .addWidget (btn_add_cli_py )
        btn_del_cli_py =QPushButton ("删除")
        btn_del_cli_py .setObjectName ("noHoverBtn")
        btn_del_cli_py .clicked .connect (self .del_cli_python )
        py_btn_row .addWidget (btn_del_cli_py )
        py_btn_row .addStretch ()
        lay .addLayout (py_btn_row )

        lay .addWidget (QLabel ("Java解释器:"))
        self .table_java =self ._make_interpreter_table ()
        lay .addWidget (self .table_java )
        java_btn_row =QHBoxLayout ()
        btn_add_cli_java =QPushButton ("新增")
        btn_add_cli_java .setObjectName ("noHoverBtn")
        btn_add_cli_java .clicked .connect (self .add_cli_java )
        java_btn_row .addWidget (btn_add_cli_java )
        btn_del_cli_java =QPushButton ("删除")
        btn_del_cli_java .setObjectName ("noHoverBtn")
        btn_del_cli_java .clicked .connect (self .del_cli_java )
        java_btn_row .addWidget (btn_del_cli_java )
        java_btn_row .addStretch ()
        lay .addLayout (java_btn_row )

        self ._refresh_interpreter_tables ()

        lay .addWidget (QLabel (""))

        # 以下截图快捷键UI已禁用
        # ss_row = QHBoxLayout()
        # ss_row.addWidget(QLabel("截图快捷键:"))
        # self.ed_screenshot_key = QLineEdit()
        # self.ed_screenshot_key.setPlaceholderText("点击后按下组合键")
        # existing_ss = SETTINGS.get("screenshot_hotkey", "")
        # if existing_ss:
        #     self.ed_screenshot_key.setText(existing_ss)
        # self.ed_screenshot_key.keyPressEvent = self._capture_screenshot_key
        # ss_row.addWidget(self.ed_screenshot_key)
        # btn_clear_ss = QPushButton("清除")
        # btn_clear_ss.setObjectName("noHoverBtn")
        # btn_clear_ss.clicked.connect(self.ed_screenshot_key.clear)
        # ss_row.addWidget(btn_clear_ss)
        # lay.addLayout(ss_row)

        # 以下快捷启动面板UI已禁用
        # qo_row = QHBoxLayout()
        # qo_row.addWidget(QLabel("快捷启动面板:"))
        # self.ed_quick_open_key = QLineEdit()
        # self.ed_quick_open_key.setPlaceholderText("点击后按下组合键")
        # existing_qo = SETTINGS.get("quick_open_hotkey", "")
        # if existing_qo:
        #     self.ed_quick_open_key.setText(existing_qo)
        # self.ed_quick_open_key.keyPressEvent = self._capture_quick_open_key
        # qo_row.addWidget(self.ed_quick_open_key)
        # btn_clear_qo = QPushButton("清除")
        # btn_clear_qo.setObjectName("noHoverBtn")
        # btn_clear_qo.clicked.connect(self.ed_quick_open_key.clear)
        # qo_row.addWidget(btn_clear_qo)
        # lay.addLayout(qo_row)

        # lay.addWidget(QLabel(""))  # 已禁用终端功能
        # lay.addWidget(QLabel("终端设置:"))

        # term_save_row = QHBoxLayout()
        # term_save_row.addWidget(QLabel("关闭标签时:"))
        # self.cb_term_save = QComboBox()
        # self.cb_term_save.addItems(["有内容时询问","总是询问","总是自动保存","总是丢弃"])
        # term_save_map = {"prompt_if_content":0,"prompt":1,"always_save":2,"always_discard":3}
        # ts_idx = term_save_map.get(SETTINGS.get("terminal_save_prompt","prompt_if_content"),0)
        # self.cb_term_save.setCurrentIndex(ts_idx)
        # term_save_row.addWidget(self.cb_term_save)
        # lay.addLayout(term_save_row)

        # term_shell_row = QHBoxLayout()
        # term_shell_row.addWidget(QLabel("默认Shell:"))
        # self.cb_term_shell = QComboBox()
        # self.cb_term_shell.addItems(["CMD","PowerShell"])
        # shell_idx = 0 if SETTINGS.get("terminal_default_shell","cmd")=="cmd" else 1
        # self.cb_term_shell.setCurrentIndex(shell_idx)
        # term_shell_row.addWidget(self.cb_term_shell)
        # lay.addLayout(term_shell_row)

        lay .addStretch ()
        scroll .setWidget (scroll_w )
        self ._fix_scroll_viewport (scroll ,scroll_w )

        tab_lay =QVBoxLayout (tab )
        tab_lay .setContentsMargins (0 ,0 ,0 ,0 )
        tab_lay .addWidget (scroll )
        self .tab_widget .addTab (tab ,"高级")

    def browse_py (self ):
        current_path =self .ed_py .text ().strip ()
        start_dir =""
        if current_path :
            start_dir =os .path .dirname (current_path )
            if not os .path .isabs (start_dir ):
                start_dir =""
        fi ,_ =QFileDialog .getOpenFileName (self ,"选择Python可执行文件",start_dir )
        if fi :
            self .ed_py .setText (fi )

    def browse_dir (self ,line_edit ):
        current_path =line_edit .text ().strip ()
        start_dir =""
        if current_path and os .path .isabs (current_path ):
            start_dir =current_path 
        d =QFileDialog .getExistingDirectory (self ,"选择目录",start_dir )
        if d :
            line_edit .setText (d )

    def _fix_scroll_viewport (self ,scroll ,content_widget =None ):
        surface =THEME .get ("surface","#000000")
        bg =QColor (surface )
        is_transparent =not bg .isValid ()or bg .alpha ()<200

        if is_transparent :
            viewport =scroll .viewport ()
            if viewport :
                viewport .setAutoFillBackground (False )
                viewport .setStyleSheet ("QWidget { background: transparent; }")
            if content_widget is not None :
                content_widget .setAutoFillBackground (False )
                content_widget .setStyleSheet ("QWidget { background: transparent; }")
            return

        hex_color =bg .name ()
        viewport =scroll .viewport ()
        if viewport :
            viewport .setObjectName ("_themeVP" )
            viewport .setStyleSheet (
            f"QWidget#_themeVP {{ background-color: {hex_color }; }}"
            )
            viewport .setAutoFillBackground (True )
            pal =viewport .palette ()
            pal .setColor (QPalette .ColorRole .Window ,bg )
            viewport .setPalette (pal )

        if content_widget is not None :
            content_widget .setObjectName ("_scrollContent" )
            content_widget .setStyleSheet (
            f"QWidget#_scrollContent {{ background-color: {hex_color }; }}"
            )
            content_widget .setAutoFillBackground (True )
            pal2 =content_widget .palette ()
            pal2 .setColor (QPalette .ColorRole .Window ,bg )
            content_widget .setPalette (pal2 )

    def _capture_hotkey_common (self ,event ,line_edit ):
        mods =[]
        if event .modifiers ()&Qt .KeyboardModifier .ControlModifier :
            mods .append ("Ctrl")
        if event .modifiers ()&Qt .KeyboardModifier .AltModifier :
            mods .append ("Alt")
        if event .modifiers ()&Qt .KeyboardModifier .ShiftModifier :
            mods .append ("Shift")
        if event .key ()in (Qt .Key .Key_Control ,Qt .Key .Key_Alt ,Qt .Key .Key_Shift ):
            return
        keystr =QKeySequence (event .key ()).toString ()
        if not keystr :
            return
        final ="+".join (mods +[keystr ])
        line_edit .setText (final )

    # def _capture_screenshot_key(self, event):  # 已禁用截图功能
    #     self._capture_hotkey_common(event, self.ed_screenshot_key)

    # def _capture_quick_open_key(self, event):  # 已禁用全局热键功能
    #     self._capture_hotkey_common(event, self.ed_quick_open_key)

    def _make_interpreter_table (self ):
        table =QTableWidget ()
        table .setColumnCount (2 )
        table .setHorizontalHeaderLabels (["名称","路径"])
        table .setSelectionBehavior (QAbstractItemView .SelectionBehavior .SelectRows )
        table .setSelectionMode (QAbstractItemView .SelectionMode .SingleSelection )
        table .setEditTriggers (QAbstractItemView .EditTrigger .NoEditTriggers )
        table .verticalHeader () .setVisible (False )
        table .horizontalHeader () .setVisible (False )
        table .setShowGrid (False )
        table .setAlternatingRowColors (True )
        table .horizontalHeader () .setStretchLastSection (True )
        table .horizontalHeader () .setSectionResizeMode (0 ,QHeaderView .ResizeMode .ResizeToContents )
        table .horizontalHeader () .setSectionResizeMode (1 ,QHeaderView .ResizeMode .Stretch )
        table .setMinimumHeight (110 )
        table .setMaximumHeight (180 )
        border =THEME .get ("border","#333")
        surface =THEME .get ("surface","#222")
        hover =THEME .get ("hover","#333")
        text_secondary =THEME .get ("text_secondary","#999")
        table .setStyleSheet (
        f"QTableWidget {{ border: 1px solid {border}; border-radius: 8px; background-color: transparent; alternate-background-color: {hover}; }}"
        f"QHeaderView::section {{ background-color: {surface}; color: {text_secondary}; border: none; padding: 6px 8px; font-weight: 600; }}"
        f"QTableWidget::item {{ padding: 4px 8px; }}"
        )
        return table 

    def _table_row_name (self ,table ,row ):
        name_item =table .item (row ,0 )
        if name_item is None :
            return ""
        return str (name_item .text ()).strip ()

    def _selected_interpreter_name (self ,table ):
        row =table .currentRow ()
        if row <0 :
            return ""
        return self ._table_row_name (table ,row )

    def _populate_interpreter_table (self ,table ,items ):
        table .setRowCount (0 )
        for item in items :
            nm =str (item .get ("name","")).strip ()
            p =str (item .get ("path","")).strip ()
            if not nm and not p :
                continue 
            row =table .rowCount ()
            table .insertRow (row )
            table .setItem (row ,0 ,QTableWidgetItem (nm ))
            table .setItem (row ,1 ,QTableWidgetItem (p ))

    def _refresh_interpreter_tables (self ):
        self ._populate_interpreter_table (self .table_py ,self .cli_python_list )
        self ._populate_interpreter_table (self .table_java ,self .cli_java_list )

    def add_cli_python (self ):
        name ,ok =QInputDialog .getText (self ,"名称","Python解释器名称：")
        if not ok or not name .strip ():
            return 
        name =name .strip ()
        norm =name .casefold ()
        for it in (self .cli_python_list or []):
            if str (it .get ("name","")).strip ().casefold ()==norm :
                QMessageBox .warning (self ,"错误","已存在同名解释器名称")
                return 
        for it in (self .cli_java_list or []):
            if str (it .get ("name","")).strip ().casefold ()==norm :
                QMessageBox .warning (self ,"错误","已存在同名解释器名称")
                return 

        path ,ok2 =QFileDialog .getOpenFileName (self ,"选择Python可执行文件")
        if not ok2 or not path :
            return 
        if not os .path .isfile (path ):
            QMessageBox .warning (self ,"错误","请选择 python.exe 可执行文件")
            return 

        self .cli_python_list .append ({"name":name ,"path":path })
        self ._refresh_interpreter_tables ()

    def del_cli_python (self ):
        nm =self ._selected_interpreter_name (self .table_py )
        if not nm :
            QMessageBox .warning (self ,"错误","没有选中要删除的Python解释器")
            return 
        msg =QMessageBox (self )
        msg .setWindowTitle ("确认删除")
        msg .setIcon (QMessageBox .Icon .Question )
        msg .setText (f"确定删除Python解释器 '{nm}' 吗？")
        msg .setStandardButtons (QMessageBox .StandardButton .Yes |QMessageBox .StandardButton .No )
        if msg .exec ()!=QMessageBox .StandardButton .Yes :
            return 
        self .cli_python_list =[x for x in self .cli_python_list if str (x .get ("name",""))!=str (nm )]
        self ._refresh_interpreter_tables ()

    def add_cli_java (self ):
        name ,ok =QInputDialog .getText (self ,"名称","Java解释器名称：")
        if not ok or not name .strip ():
            return 
        name =name .strip ()
        norm =name .casefold ()
        for it in (self .cli_java_list or []):
            if str (it .get ("name","")).strip ().casefold ()==norm :
                QMessageBox .warning (self ,"错误","已存在同名解释器名称")
                return 
        for it in (self .cli_python_list or []):
            if str (it .get ("name","")).strip ().casefold ()==norm :
                QMessageBox .warning (self ,"错误","已存在同名解释器名称")
                return 

        path =QFileDialog .getExistingDirectory (self ,"选择Java目录")
        if not path :
            return 
        if not os .path .isdir (path ):
            QMessageBox .warning (self ,"错误","Java路径请选择目录")
            return 

        self .cli_java_list .append ({"name":name ,"path":path })
        self ._refresh_interpreter_tables ()

    def del_cli_java (self ):
        nm =self ._selected_interpreter_name (self .table_java )
        if not nm :
            QMessageBox .warning (self ,"错误","没有选中要删除的Java解释器")
            return 
        msg =QMessageBox (self )
        msg .setWindowTitle ("确认删除")
        msg .setIcon (QMessageBox .Icon .Question )
        msg .setText (f"确定删除Java解释器 '{nm}' 吗？")
        msg .setStandardButtons (QMessageBox .StandardButton .Yes |QMessageBox .StandardButton .No )
        if msg .exec ()!=QMessageBox .StandardButton .Yes :
            return 
        self .cli_java_list =[x for x in self .cli_java_list if str (x .get ("name",""))!=str (nm )]
        self ._refresh_interpreter_tables ()

    def _on_health_check (self ):
        try :
            from services .tool_health import ToolHealthChecker
            from config import load_tools
            tools =load_tools ()
            checker =ToolHealthChecker ()
            status =checker .check_all (tools )
            missing =sum (1 for v in status .values ()if v =="missing")
            ok =sum (1 for v in status .values ()if v =="ok")
            self ._health_result_label .setText (f"共 {len(status)} 个工具: {ok} 正常, {missing} 缺失")
            self ._health_result_label .setStyleSheet (
                "color: #4CAF50; font-size: 11px;" if missing ==0 else "color: #FF8C00; font-size: 11px;"
            )
            if missing >0 :
                missing_names =[k for k ,v in status .items ()if v =="missing"]
                QMessageBox .information (
                self ,"健康检查结果",
                f"共 {len(status)} 个工具\n正常: {ok}\n缺失: {missing}\n\n缺失工具:\n" +
                "\n".join (missing_names [:20 ])
                )
            else :
                QMessageBox .information (self ,"健康检查结果",f"共 {len(status)} 个工具，全部正常！")
        except Exception as e :
            self ._health_result_label .setText (f"检查失败: {e}")
            self ._health_result_label .setStyleSheet ("color: #EF4444; font-size: 11px;")

    def save_settings (self ):
        from config import SETTINGS ,save_settings

        new_s =dict (SETTINGS )
        new_s ["python_path"]=self .ed_py .text ().strip ()
        new_s ["java8_path"]=self .ed_j8 .text ().strip ()
        new_s ["java11_path"]=self .ed_j11 .text ().strip ()
        new_s ["display_mode"]="scroll"

        new_s ["cli_python_interpreters"]=list (self .cli_python_list )
        new_s ["cli_java_interpreters"]=list (self .cli_java_list )

        # new_s["screenshot_hotkey"] = self.ed_screenshot_key.text().strip()  # 已禁用截图功能
        # new_s["quick_open_hotkey"] = self.ed_quick_open_key.text().strip()  # 已禁用全局热键功能

        # term_save_map = {"有内容时询问":"prompt_if_content","总是询问":"prompt","总是自动保存":"always_save","总是丢弃":"always_discard"}  # 已禁用终端功能
        # new_s["terminal_save_prompt"] = term_save_map.get(self.cb_term_save.currentText(), "prompt_if_content")
        # new_s["terminal_default_shell"] = "cmd" if self.cb_term_shell.currentText() == "CMD" else "powershell"
        # new_s["terminal_font_size"] = 10

        if save_settings (new_s ):
            self .settings_changed .emit (new_s )

        self .accept ()
