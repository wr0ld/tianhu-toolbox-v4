import logging 
import sys 
import os 
import subprocess 
import re 
import html 
from PyQt6 .QtCore import Qt ,QAbstractListModel ,QModelIndex ,pyqtSignal ,QSize ,QRect ,QPoint ,QEvent ,QRectF ,QVariantAnimation ,QEasingCurve ,QTimer 
from PyQt6 .QtGui import QPainter ,QColor ,QFont ,QPen ,QBrush ,QPixmap ,QIcon ,QMouseEvent ,QPainterPath ,QLinearGradient 
from PyQt6 .QtWidgets import QListView ,QStyledItemDelegate ,QApplication ,QMenu ,QStyle ,QToolTip ,QWidget ,QVBoxLayout ,QLabel ,QGraphicsDropShadowEffect 

import config 
from config import SETTINGS 
from utils import is_tool_favorited ,add_favorite_tool ,remove_favorite_tool 

logger =logging .getLogger (__name__ )


_RGBA_RE =re .compile (
r"^rgba\(\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*([0-9]*\.?[0-9]+)\s*\)$",
re .IGNORECASE ,
)


def _theme_qcolor (value :str )->QColor :
    if not isinstance (value ,str )or not value :
        return QColor ()

    m =_RGBA_RE .match (value .strip ())
    if m :
        r ,g ,b =(int (m .group (1 )),int (m .group (2 )),int (m .group (3 )))
        a_raw =float (m .group (4 ))

        if a_raw <=1.0 :
            a =int (max (0.0 ,min (1.0 ,a_raw ))*255 )
        else :
            a =int (max (0.0 ,min (255.0 ,a_raw )))
        return QColor (r ,g ,b ,a )

    return QColor (value )


class TooltipPopup (QWidget ):
    def __init__ (self ,parent =None ):
        super ().__init__ (None ,Qt .WindowType .ToolTip |Qt .WindowType .FramelessWindowHint )
        self .setAttribute (Qt .WidgetAttribute .WA_TranslucentBackground ,True )
        self .setAttribute (Qt .WidgetAttribute .WA_ShowWithoutActivating ,True )
        self .setFocusPolicy (Qt .FocusPolicy .NoFocus )
        self ._content =QWidget (self )
        self ._content .setObjectName ("tooltipPopupContent")

        layout =QVBoxLayout (self )
        layout .setContentsMargins (0 ,0 ,0 ,0 )
        layout .addWidget (self ._content )

        c_layout =QVBoxLayout (self ._content )
        c_layout .setContentsMargins (12 ,10 ,12 ,10 )
        c_layout .setSpacing (0 )

        self ._label =QLabel (self ._content )
        self ._label .setTextFormat (Qt .TextFormat .RichText )
        self ._label .setTextInteractionFlags (Qt .TextInteractionFlag .NoTextInteraction )
        self ._label .setWordWrap (True )
        c_layout .addWidget (self ._label )

        effect =QGraphicsDropShadowEffect (self )
        effect .setBlurRadius (26 )
        effect .setOffset (0 ,8 )
        effect .setColor (QColor (0 ,0 ,0 ,160 ))
        self ._content .setGraphicsEffect (effect )

        self ._anim =QVariantAnimation (self )
        self ._anim .setDuration (160 )
        self ._anim .setEasingCurve (QEasingCurve .Type .OutCubic )
        self ._base_pos =QPoint ()
        self ._lift =10 

        def _on_val (v ):
            t =float (v )
            self .setWindowOpacity (t )
            self .move (self ._base_pos .x (),self ._base_pos .y ()+int (self ._lift *(1.0 -t )))

        self ._anim .valueChanged .connect (_on_val )

    def set_html (self ,html_text :str ):
        self ._label .setText (html_text )
        self ._label .adjustSize ()
        self ._content .adjustSize ()
        self .adjustSize ()

    def _apply_theme (self ):
        try :
            theme =getattr (config ,"THEME",{})or {}
            bg =_theme_qcolor (str (theme .get ('card_bg','rgba(30,30,30,0.92)')))
            text =_theme_qcolor (str (theme .get ('text','#E7E7F2')))
            primary =_theme_qcolor (str (theme .get ('primary','rgba(120,120,255,0.9)')))
            border_v =theme .get ('border',None )
            if not border_v :
                border_v =theme .get ('primary','rgba(120,120,255,0.45)')
            border =_theme_qcolor (str (border_v ))
        except Exception :
            bg =QColor (30 ,30 ,30 ,235 )
            text =QColor (231 ,231 ,242 )
            primary =QColor (120 ,120 ,255 ,220 )
            border =QColor (120 ,120 ,255 ,140 )

        bg2 =QColor (bg )
        try :
            bg2 .setAlpha (min (255 ,bg .alpha ()+18 ))
        except Exception :
            pass 

        self ._content .setStyleSheet (
        "QWidget#tooltipPopupContent {"
        f"background-color: rgba({bg .red ()},{bg .green ()},{bg .blue ()},{bg .alpha ()});"
        f"border: 1px solid rgba({border .red ()},{border .green ()},{border .blue ()},{border .alpha ()});"
        "border-radius: 14px;"
        "}"
        )
        self ._label .setStyleSheet (
        "QLabel {"
        f"color: rgba({text .red ()},{text .green ()},{text .blue ()},{text .alpha ()});"
        "font-size: 12px;"
        "}"
        "QLabel a {"
        f"color: rgba({primary .red ()},{primary .green ()},{primary .blue ()},{primary .alpha ()});"
        "text-decoration: none;"
        "}"
        )

    def show_near_rect (self ,anchor_pos :QPoint ,anchor_rect :QRect ):
        self ._apply_theme ()
        self .adjustSize ()

        screen =None 
        try :
            screen =QApplication .screenAt (anchor_pos )
        except Exception :
            screen =None 
        if screen is None :
            try :
                screen =QApplication .primaryScreen ()
            except Exception :
                screen =None 

        if screen is not None :
            g =screen .availableGeometry ()
        else :
            g =QRect (0 ,0 ,1920 ,1080 )

        margin =12 
        w =self .width ()
        h =self .height ()

        x =anchor_pos .x ()-w //2 
        y =anchor_pos .y ()+anchor_rect .height ()//2 +10 

        if y +h +margin >g .bottom ():
            y =anchor_pos .y ()-anchor_rect .height ()//2 -h -10 

        if x <g .left ()+margin :
            x =g .left ()+margin 
        if x +w +margin >g .right ():
            x =g .right ()-w -margin 
        if y <g .top ()+margin :
            y =g .top ()+margin 
        if y +h +margin >g .bottom ():
            y =g .bottom ()-h -margin 

        self ._base_pos =QPoint (x ,y )

        try :
            self ._anim .stop ()
        except Exception :
            pass 

        self .setWindowOpacity (0.0 )
        self .move (x ,y +self ._lift )
        self .show ()
        self .raise_ ()
        self ._anim .setStartValue (0.0 )
        self ._anim .setEndValue (1.0 )
        self ._anim .start ()

    def hide_immediately (self ):
        try :
            self ._anim .stop ()
        except Exception :
            pass 
        try :
            self .hide ()
        except Exception :
            pass 

class ToolModel (QAbstractListModel ):
    def __init__ (self ,tools =None ):
        super ().__init__ ()
        self ._tools =tools or []

    def rowCount (self ,parent =QModelIndex ()):
        return len (self ._tools )

    def data (self ,index ,role =Qt .ItemDataRole .DisplayRole ):
        if not index .isValid ()or index .row ()>=len (self ._tools ):
            return None 

        tool =self ._tools [index .row ()]

        if role ==Qt .ItemDataRole .DisplayRole :
            return tool ['name']
        elif role ==Qt .ItemDataRole .UserRole :
            return tool 

        return None 

    def set_tools (self ,tools ):
        self .beginResetModel ()
        self ._tools =tools 
        self .endResetModel ()

    def get_tool (self ,index ):
        if 0 <=index .row ()<len (self ._tools ):
            return self ._tools [index .row ()]
        return None 

class ToolDelegate (QStyledItemDelegate ):
    run_clicked =pyqtSignal (dict )
    edit_clicked =pyqtSignal (dict )
    delete_clicked =pyqtSignal (dict )
    fav_clicked =pyqtSignal (dict )

    def __init__ (self ,parent =None ):
        super ().__init__ (parent )
        self .padding =8 
        self .spacing =4 


        self .btn_run_rect =QRect ()
        self .btn_fav_rect =QRect ()

    def paint (self ,painter ,option ,index ):
        tool =index .data (Qt .ItemDataRole .UserRole )
        if not tool :
            return 

        painter .save ()
        painter .setRenderHint (QPainter .RenderHint .Antialiasing )


        try :
            if SETTINGS .get ("theme")=="liquid_glass":
                parent =self .parent ()
                global_t =float (getattr (parent ,"_lg_reveal_t",1.0 )or 1.0 )
                anchor_row =int (getattr (parent ,"_lg_reveal_anchor_row",0 )or 0 )
                row =index .row ()
                hover_idx =getattr (parent ,"_lg_hover_index",None )
                hover_prog =float (getattr (parent ,"_lg_hover_progress",0.0 )or 0.0 )
                is_this_hover =hover_idx is not None and hover_idx .isValid ()and hover_idx .row ()==row 

                try :
                    item_reveal =getattr (parent ,"_lg_item_reveal",None )
                    item_reveal_t =1.0 
                    if isinstance (item_reveal ,dict ):
                        item_reveal_t =float (item_reveal .get (row ,1.0 ))
                except Exception :
                    item_reveal_t =1.0 

                opacity =1.0 
                lift =0.0 


                if global_t <1.0 :
                    stagger =0.028 
                    cap =12 
                    rel =row -anchor_row 
                    if rel <0 :
                        rel =0 
                    eff_row =rel if rel <cap else cap 
                    item_t =(global_t -eff_row *stagger )/0.72 
                    if item_t <0.0 :
                        item_t =0.0 
                    elif item_t >1.0 :
                        item_t =1.0 
                    opacity *=(0.16 +0.84 *item_t )
                    lift +=12.0 *(1.0 -item_t )


                try :
                    if SETTINGS .get ("display_mode","scroll")!="paged":
                        vh =max (1 ,int (parent .viewport ().height ()))
                        appear_zone =180.0 
                        d =float (vh -option .rect .top ())
                        if d <appear_zone :
                            sf =max (0.0 ,min (1.0 ,d /appear_zone ))
                            opacity *=(0.35 +0.65 *sf )
                            lift +=6.0 *(1.0 -sf )
                except Exception :
                    pass 


                try :
                    if SETTINGS .get ("display_mode","scroll")!="paged"and item_reveal_t <1.0 :
                        opacity *=(0.22 +0.78 *item_reveal_t )
                        lift +=10.0 *(1.0 -item_reveal_t )
                except Exception :
                    pass 


                if is_this_hover and hover_prog >0.0 :
                    lift -=6.0 *hover_prog 

                if opacity <0.999 :
                    painter .setOpacity (opacity )
                if abs (lift )>0.01 :
                    painter .translate (0.0 ,lift )
        except Exception :
            pass 


        rect =option .rect 

        card_rect =rect .adjusted (1 ,1 ,-1 ,-1 )


        bg_color =_theme_qcolor (config .THEME ['card_bg'])
        border_color =_theme_qcolor (config .THEME ['border'])
        text_color =_theme_qcolor (config .THEME ['text'])
        primary_color =_theme_qcolor (config .THEME ['primary'])


        is_hover =(option .state &QStyle .StateFlag .State_MouseOver )
        is_selected =(option .state &QStyle .StateFlag .State_Selected )


        show_selection =is_selected 
        if hasattr (self .parent (),"show_select_box"):
            if not self .parent ().show_select_box :
                show_selection =False 

        if show_selection :
            bg_color =_theme_qcolor (config .THEME ['selected'])
            border_color =primary_color 
        elif is_hover :
            bg_color =_theme_qcolor (config .THEME ['hover'])
            border_color =primary_color 


        path =QPainterPath ()
        path .addRoundedRect (QRectF (card_rect ),12 ,12 )

        painter .setPen (QPen (border_color ,1 ))
        painter .setBrush (bg_color )
        painter .drawPath (path )


        try :
            if SETTINGS .get ("theme")=="liquid_glass":
                parent =self .parent ()
                hover_idx =getattr (parent ,"_lg_hover_index",None )
                prog =float (getattr (parent ,"_lg_hover_progress",0.0 )or 0.0 )
                if hover_idx is not None and hover_idx .isValid ()and hover_idx .row ()==index .row ()and prog >0.0 :
                    g =QLinearGradient (card_rect .topLeft (),card_rect .bottomRight ())

                    g .setColorAt (0.0 ,QColor (255 ,255 ,255 ,int (70 *prog )))
                    g .setColorAt (0.35 ,QColor (255 ,255 ,255 ,int (30 *prog )))
                    g .setColorAt (1.0 ,QColor (0 ,122 ,255 ,int (18 *prog )))

                    painter .setPen (Qt .PenStyle .NoPen )
                    painter .setBrush (QBrush (g ))
                    painter .drawPath (path )


                    painter .setBrush (Qt .BrushStyle .NoBrush )
                    painter .setPen (QPen (QColor (255 ,255 ,255 ,int (85 *prog )),1 ))
                    painter .drawPath (path )
        except Exception :
            pass 


        if show_selection :

            check_size =24 
            check_rect =QRect (card_rect .right ()-check_size -8 ,card_rect .bottom ()-check_size -8 ,check_size ,check_size )
            painter .setPen (Qt .PenStyle .NoPen )
            painter .setBrush (primary_color )
            painter .drawEllipse (check_rect )


            painter .setPen (QPen (QColor ("white"),2 ))
            painter .drawLine (
            check_rect .left ()+6 ,check_rect .top ()+12 ,
            check_rect .left ()+10 ,check_rect .bottom ()-8 
            )
            painter .drawLine (
            check_rect .left ()+10 ,check_rect .bottom ()-8 ,
            check_rect .right ()-6 ,check_rect .top ()+8 
            )


        content_rect =card_rect .adjusted (self .padding ,self .padding ,-self .padding ,-self .padding )


        health_status =str (tool .get ("_health","ok"))
        dot_radius =5
        dot_cx =content_rect .left ()+dot_radius +3
        dot_cy =content_rect .top ()+11
        dot_color =QColor ("#10B981")if health_status =="ok" else QColor ("#EF4444")
        painter .save ()
        glow_color =QColor (dot_color )
        glow_color .setAlpha (50 )
        painter .setPen (Qt .PenStyle .NoPen )
        painter .setBrush (glow_color )
        painter .drawEllipse (QPoint (dot_cx ,dot_cy ),dot_radius +3 ,dot_radius +3 )
        painter .setBrush (dot_color )
        painter .drawEllipse (QPoint (dot_cx ,dot_cy ),dot_radius ,dot_radius )
        highlight =QColor (255 ,255 ,255 ,80 )
        painter .setBrush (highlight )
        painter .drawEllipse (QPoint (dot_cx -1 ,dot_cy -1 ),2 ,2 )
        painter .restore ()


        header_height =24
        name_rect =QRect (content_rect .left ()+16 ,content_rect .top (),content_rect .width ()-80 ,header_height )
        weight_rect =QRect (content_rect .right ()-58 ,content_rect .top ()+4 ,22 ,16 )
        fav_rect =QRect (content_rect .right ()-24 ,content_rect .top (),24 ,24 )


        painter .setPen (text_color )
        font_name =painter .font ()
        font_name .setBold (True )
        font_name .setPointSize (11 )
        painter .setFont (font_name )
        name_text =painter .fontMetrics ().elidedText (str (tool .get ('name','')),Qt .TextElideMode .ElideRight ,name_rect .width ())
        painter .drawText (name_rect ,Qt .AlignmentFlag .AlignLeft |Qt .AlignmentFlag .AlignVCenter ,name_text )


        try :
            w =tool .get ("weight",None )
            if isinstance (w ,int )or (isinstance (w ,str )and str (w ).isdigit ()):
                w =int (w )
                badge_bg =QColor (primary_color )
                badge_bg .setAlpha (28 )
                badge_bd =QColor (primary_color )
                badge_bd .setAlpha (90 )
                painter .setPen (QPen (badge_bd ,1 ))
                painter .setBrush (badge_bg )
                painter .drawRoundedRect (weight_rect ,8 ,8 )
                painter .setPen (primary_color )
                painter .setFont (QFont ("Segoe UI",8 ,QFont .Weight .Bold ))
                painter .drawText (weight_rect ,Qt .AlignmentFlag .AlignCenter ,str (w ))
        except Exception :
            pass 


        is_fav =is_tool_favorited (tool )
        fav_text ="★"if is_fav else "☆"
        painter .setPen (QColor ("#FFD700")if is_fav else _theme_qcolor (config .THEME ['text_secondary']))
        painter .setFont (QFont ("Segoe UI Emoji",12 ))
        painter .drawText (fav_rect ,Qt .AlignmentFlag .AlignCenter ,fav_text )


        tags =tool .get ("tags",[])[:3 ]
        tag_y =content_rect .top ()+header_height +4 
        tag_height =18 

        painter .setFont (QFont ("Segoe UI",8 ))
        tag_x =content_rect .left ()
        for tag in tags :
            tag_text =f"#{tag[:10]}"
            tag_width =painter .fontMetrics ().horizontalAdvance (tag_text )+10 
            tag_rect =QRect (tag_x ,tag_y ,tag_width ,tag_height )

            painter .setPen (Qt .PenStyle .NoPen )
            painter .setBrush (_theme_qcolor (config .THEME ['surface']))
            painter .drawRoundedRect (tag_rect ,4 ,4 )

            painter .setPen (_theme_qcolor (config .THEME ['text_secondary']))
            painter .drawText (tag_rect ,Qt .AlignmentFlag .AlignCenter ,tag_text )

            tag_x +=tag_width +4 


        desc_y =tag_y +tag_height +6 
        desc_height =36 
        desc_rect =QRect (content_rect .left (),desc_y ,content_rect .width (),desc_height )

        desc_text =tool .get ("description","")
        if desc_text :
            painter .setPen (_theme_qcolor (config .THEME ['text_secondary']))
            painter .setFont (QFont ("Segoe UI",9 ))
            painter .drawText (desc_rect ,Qt .TextFlag .TextWordWrap |Qt .AlignmentFlag .AlignTop ,desc_text )


        footer_height =28 
        footer_y =card_rect .bottom ()-self .padding -footer_height 


        tool_type_str = str(tool.get("type", ""))
        type_short_map = {
            "Python": "PY", "JAVA8": "J8", "JAVA8图形化": "J8G",
            "JAVA11": "J11", "JAVA11图形化": "J11G",
            "GUI应用": "GUI", "命令行": "CLI", "批处理": "BAT",
            "PowerShell": "PS", "网页": "WEB",
        }
        type_label = type_short_map.get(tool_type_str, tool_type_str[:3] if tool_type_str else "")
        # if type_label:
        #     type_font = QFont("Segoe UI", 8, QFont.Weight.Bold)
        #     painter.setFont(type_font)
        #     type_text_w = painter.fontMetrics().horizontalAdvance(type_label) + 10
        #     type_badge_rect = QRect(content_rect.left(), footer_y + 4, type_text_w, 18)
        #     type_bg = QColor(primary_color)
        #     type_bg.setAlpha(35)
        #     type_bd = QColor(primary_color)
        #     type_bd.setAlpha(100)
        #     painter.setPen(QPen(type_bd, 1))
        #     painter.setBrush(type_bg)
        #     painter.drawRoundedRect(type_badge_rect, 4, 4)
        #     painter.setPen(_theme_qcolor(config.THEME['primary']))
        #     painter.drawText(type_badge_rect, Qt.AlignmentFlag.AlignCenter, type_label)
        #     cat_left = content_rect.left() + type_text_w + 6
        # else:
        cat_left = content_rect.left()

        # cat_rect = QRect(cat_left, footer_y, content_rect.width() - 70 - (cat_left - content_rect.left()), footer_height)
        # painter.setPen(_theme_qcolor(config.THEME['primary']))
        # painter.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        # cat_text = f"📁 {tool['category']}"
        # cat_text = painter.fontMetrics().elidedText(cat_text, Qt.TextElideMode.ElideRight, cat_rect.width())
        # painter.drawText(cat_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, cat_text)

        painter .restore ()

    def sizeHint (self ,option ,index ):

        return QSize (250 ,75 )

    def editorEvent (self ,event ,model ,option ,index ):
        if event .type ()==QEvent .Type .MouseButtonRelease :
            mouse_event =event 
            pos =mouse_event .position ().toPoint ()


            rect =option .rect 
            card_rect =rect .adjusted (1 ,1 ,-1 ,-1 )
            content_rect =card_rect .adjusted (self .padding ,self .padding ,-self .padding ,-self .padding )


            fav_rect =QRect (content_rect .right ()-24 ,content_rect .top (),24 ,24 )
            if fav_rect .contains (pos ):
                tool =index .data (Qt .ItemDataRole .UserRole )
                self .fav_clicked .emit (tool )
                return True 

        return False 

class ModernToolGrid (QListView ):
    tool_run =pyqtSignal (dict )
    tool_edit =pyqtSignal (dict )
    tool_delete =pyqtSignal (dict )
    favorite_changed =pyqtSignal (dict ,bool )
    batch_run_requested =pyqtSignal (list )

    def __init__ (self ,parent =None ):
        super ().__init__ (parent )
        self .setViewMode (QListView .ViewMode .IconMode )
        self .setResizeMode (QListView .ResizeMode .Adjust )
        self .setUniformItemSizes (True )
        self .setSpacing (3 )
        self .setMouseTracking (True )
        self .viewport ().setMouseTracking (True )

        self .setStyleSheet ("QListView { background: transparent; border: none; }")

        self .tool_model =ToolModel ()
        self .setModel (self .tool_model )

        self .delegate =ToolDelegate (self )
        self .setItemDelegate (self .delegate )


        self ._lg_hover_index =QModelIndex ()
        self ._lg_hover_progress =0.0 
        self ._lg_hover_anim =None 


        self ._lg_reveal_t =1.0 
        self ._lg_reveal_anim =None 

        self .setMouseTracking (True )
        try :
            self .entered .connect (self ._on_item_entered )
        except Exception :
            pass 


        self .delegate .run_clicked .connect (self .tool_run .emit )
        self .delegate .fav_clicked .connect (self .on_fav_clicked )

        self .doubleClicked .connect (self ._on_double_clicked )

        self .show_select_box =False 

        self ._hovering_run_button =False 

        self ._tip_timer =QTimer (self )
        self ._tip_timer .setSingleShot (True )
        self ._tip_timer .timeout .connect (self ._show_hover_tooltip )
        self ._tip_index =QModelIndex ()
        self ._tip_popup =TooltipPopup (self )

        self ._lg_item_reveal ={}
        self ._lg_item_reveal_timer =QTimer (self )
        self ._lg_item_reveal_timer .setInterval (16 )
        self ._lg_item_reveal_timer .timeout .connect (self ._lg_tick_item_reveal )

        try :
            self .verticalScrollBar ().valueChanged .connect (lambda _ =None :self ._lg_update_item_reveal_targets ())
        except Exception :
            pass 

    def _hit_test_run_button (self ,pos :QPoint )->bool :
        try :
            if self .show_select_box :
                return False 
            idx =self .indexAt (pos )
            if not idx .isValid ():
                return False 


            rect =self .visualRect (idx )
            card_rect =rect .adjusted (1 ,1 ,-1 ,-1 )
            content_rect =card_rect .adjusted (self .delegate .padding ,self .delegate .padding ,-self .delegate .padding ,-self .delegate .padding )

            footer_height =28 
            footer_y =card_rect .bottom ()-self .delegate .padding -footer_height 
            run_btn_rect =QRect (content_rect .right ()-60 ,footer_y ,60 ,26 )
            return run_btn_rect .contains (pos )
        except Exception :
            return False 

    def mouseMoveEvent (self ,e :QMouseEvent ):
        try :
            over_run =self ._hit_test_run_button (e .pos ())
            if over_run !=self ._hovering_run_button :
                self ._hovering_run_button =over_run 
                if over_run :
                    self .viewport ().setCursor (Qt .CursorShape .PointingHandCursor )
                else :
                    self .viewport ().unsetCursor ()
        except Exception :
            pass 


        try :
            if SETTINGS .get ("theme")=="liquid_glass":
                pos =e .pos ()
                idx =self .indexAt (pos )
                if not idx .isValid ():
                    if self ._lg_hover_index .isValid ()or self ._lg_hover_progress :
                        self ._lg_set_hover_index (QModelIndex ())
                else :
                    rect =self .visualRect (idx )
                    card_rect =rect .adjusted (1 ,1 ,-1 ,-1 )
                    if not card_rect .contains (pos ):
                        if self ._lg_hover_index .isValid ()or self ._lg_hover_progress :
                            self ._lg_set_hover_index (QModelIndex ())
        except Exception :
            pass 

        try :
            pos =e .pos ()
            idx =self .indexAt (pos )
            if not idx .isValid ():
                self ._cancel_hover_tooltip ()
            else :
                rect =self .visualRect (idx )
                card_rect =rect .adjusted (1 ,1 ,-1 ,-1 )
                if not card_rect .contains (pos ):
                    self ._cancel_hover_tooltip ()
        except Exception :
            pass 
        super ().mouseMoveEvent (e )

    def leaveEvent (self ,e ):
        self ._cancel_hover_tooltip ()
        try :
            if self ._hovering_run_button :
                self ._hovering_run_button =False 
                self .viewport ().unsetCursor ()
        except Exception :
            pass 
        try :

            if SETTINGS .get ("theme")=="liquid_glass":
                if self ._lg_hover_anim is not None :
                    try :
                        self ._lg_hover_anim .stop ()
                    except Exception :
                        pass 
                self ._lg_hover_index =QModelIndex ()
                self ._lg_hover_progress =0.0 
                self .viewport ().update ()
            else :
                self ._lg_set_hover_index (QModelIndex ())
        except Exception :
            pass 
        super ().leaveEvent (e )

    def wheelEvent (self ,e ):
        self ._cancel_hover_tooltip ()
        try :
            self ._lg_update_item_reveal_targets ()
        except Exception :
            pass 
        super ().wheelEvent (e )

    def _on_item_entered (self ,index :QModelIndex ):
        try :
            self ._lg_set_hover_index (index )
        except Exception :
            pass 

        try :
            self ._start_hover_tooltip (index )
        except Exception :
            pass 

    def _start_hover_tooltip (self ,index :QModelIndex ):
        if not index .isValid ():
            self ._cancel_hover_tooltip ()
            return 
        if self ._tip_index .isValid ()and self ._tip_index .row ()==index .row ():
            return 
        self ._cancel_hover_tooltip ()
        self ._tip_index =index 
        self ._tip_timer .start (3000 )

    def _cancel_hover_tooltip (self ):
        try :
            if getattr (self ,"_tip_popup",None )is not None :
                self ._tip_popup .hide_immediately ()
            else :
                QToolTip .hideText ()
        except Exception :
            pass 
        try :
            if self ._tip_timer .isActive ():
                self ._tip_timer .stop ()
        except Exception :
            pass 
        self ._tip_index =QModelIndex ()

    def _show_hover_tooltip (self ):
        try :
            if not self ._tip_index .isValid ():
                return 
            tool =self ._tip_index .data (Qt .ItemDataRole .UserRole )
            if not tool :
                return 
            rect =self .visualRect (self ._tip_index )
            if not rect .isValid ():
                return 
            pos =self .mapToGlobal (rect .center ())
            name =str (tool .get ('name',''))
            cat =str (tool .get ('category',''))
            typ =str (tool .get ('type',''))
            w =tool .get ('weight','')
            desc =str (tool .get ('description',''))
            path =str (tool .get ('path',''))
            url =str (tool .get ('url',''))
            tags =tool .get ('tags',[])or []
            tags_str =', '.join ([str (t )for t in tags if str (t ).strip ()])

            def esc (v ):
                return html .escape (str (v ))

            rows =[
            ("分类",cat ),
            ("类型",typ ),
            ]
            if w !="":
                rows .append (("权重",w ))
            if tags_str :
                rows .append (("标签",tags_str ))
            if desc :
                rows .append (("描述",desc ))
            if url :
                rows .append (("URL",url ))
            if path :
                rows .append (("路径",path ))

            rows_html ="".join ([
            f"<tr><td style='padding:2px 10px 2px 0; opacity:0.75; white-space:nowrap;'><b>{esc (k )}</b></td>"
            f"<td style='padding:2px 0; max-width:420px;'>{esc (v )}</td></tr>"
            for (k ,v )in rows 
            ])

            text =(
            "<div style='min-width: 280px; max-width: 520px;'>"
            f"<div style='font-size:13px; font-weight:700; margin-bottom:6px;'>{esc (name )}</div>"
            "<table style='border-collapse:collapse; font-size:12px; line-height:1.35;'>"
            f"{rows_html}"
            "</table>"
            "</div>"
            )
            if getattr (self ,"_tip_popup",None )is not None :
                self ._tip_popup .set_html (text )
                self ._tip_popup .show_near_rect (pos ,rect )
            else :
                QToolTip .showText (pos ,text ,self ,rect )
        except Exception :
            pass 

    def _lg_set_hover_index (self ,index :QModelIndex ):
        if SETTINGS .get ("theme")!="liquid_glass":
            return 


        if not index .isValid ():
            if self ._lg_hover_anim is not None :
                try :
                    self ._lg_hover_anim .stop ()
                except Exception :
                    pass 
            self ._lg_hover_index =QModelIndex ()
            self ._lg_hover_progress =0.0 
            self .viewport ().update ()
            return 


        start =float (self ._lg_hover_progress or 0.0 )
        end =1.0 if index .isValid ()else 0.0 
        self ._lg_hover_index =index 

        if self ._lg_hover_anim is None :
            anim =QVariantAnimation (self )
            anim .setDuration (140 )
            anim .setEasingCurve (QEasingCurve .Type .OutCubic )
            self ._lg_hover_anim =anim 

            def _on_val (v ):
                self ._lg_hover_progress =float (v )
                self .viewport ().update ()

            anim .valueChanged .connect (_on_val )

        anim =self ._lg_hover_anim 
        try :
            anim .stop ()
        except Exception :
            pass 
        try :
            if end >=start :
                anim .setDuration (120 )
            else :
                anim .setDuration (90 )
        except Exception :
            pass 
        anim .setStartValue (start )
        anim .setEndValue (end )
        anim .start ()

    def _on_double_clicked (self ,index :QModelIndex ):
        if not index .isValid ():
            return
        tool =index .data (Qt .ItemDataRole .UserRole )
        if tool :
            self .tool_run .emit (tool )

    def set_final_tools (self ,tools ):
        self .tool_model .set_tools (tools )

        self .scrollTo (self .tool_model .index (0 ,0 ))


        try :
            self ._lg_start_reveal_animation ()
        except Exception :
            pass 

        try :
            self ._lg_update_item_reveal_targets (reset =True )
        except Exception :
            pass 

    def _lg_update_item_reveal_targets (self ,reset =False ):
        if SETTINGS .get ("theme")!="liquid_glass":
            return 
        if SETTINGS .get ("display_mode","scroll")=="paged":
            return 

        if reset :
            try :
                self ._lg_item_reveal .clear ()
            except Exception :
                self ._lg_item_reveal ={}

        try :
            model =self .model ()
            if model is None :
                return 
        except Exception :
            return 

        try :
            vp =self .viewport ()
            try :
                h =int (self .gridSize ().height ())
            except Exception :
                h =160 
            h =max (1 ,h )
            step =max (1 ,h )
            visible =[]
            y =2 
            while y <vp .height ():
                idx =self .indexAt (QPoint (2 ,y ))
                if idx .isValid ():
                    visible .append (idx .row ())
                y +=step 
            if not visible :
                idx =self .indexAt (QPoint (2 ,2 ))
                if idx .isValid ():
                    visible =[idx .row ()]
        except Exception :
            return 

        changed =False 
        for r in visible :
            if r not in self ._lg_item_reveal :
                self ._lg_item_reveal [r ]=0.0 
                changed =True 

        try :
            if len (self ._lg_item_reveal )>220 :
                keep =set (visible )
                for k in list (self ._lg_item_reveal .keys ()):
                    if k not in keep and self ._lg_item_reveal .get (k ,1.0 )>=1.0 :
                        self ._lg_item_reveal .pop (k ,None )
                        if len (self ._lg_item_reveal )<=220 :
                            break 
        except Exception :
            pass 

        if changed :
            if not self ._lg_item_reveal_timer .isActive ():
                self ._lg_item_reveal_timer .start ()
            self .viewport ().update ()

    def _lg_tick_item_reveal (self ):
        try :
            if SETTINGS .get ("theme")!="liquid_glass"or SETTINGS .get ("display_mode","scroll")=="paged":
                self ._lg_item_reveal_timer .stop ()
                return 
        except Exception :
            return 

        done =True 
        try :
            for k in list (self ._lg_item_reveal .keys ()):
                v =float (self ._lg_item_reveal .get (k ,1.0 ))
                if v <1.0 :
                    v +=0.085 
                    if v >1.0 :
                        v =1.0 
                    self ._lg_item_reveal [k ]=v 
                if self ._lg_item_reveal .get (k ,1.0 )<1.0 :
                    done =False 
        except Exception :
            done =True 

        try :
            self .viewport ().update ()
        except Exception :
            pass 
        if done :
            try :
                self ._lg_item_reveal_timer .stop ()
            except Exception :
                pass 

    def _lg_start_reveal_animation (self ):
        if SETTINGS .get ("theme")!="liquid_glass":
            self ._lg_reveal_t =1.0 
            return 

        try :
            idx0 =self .indexAt (QPoint (2 ,2 ))
            if idx0 .isValid ():
                self ._lg_reveal_anchor_row =int (idx0 .row ())
            else :
                self ._lg_reveal_anchor_row =0 
        except Exception :
            self ._lg_reveal_anchor_row =0 

        if self ._lg_reveal_anim is None :
            anim =QVariantAnimation (self )
            anim .setDuration (520 )
            anim .setEasingCurve (QEasingCurve .Type .OutCubic )
            self ._lg_reveal_anim =anim 

            def _on_val (v ):
                self ._lg_reveal_t =float (v )
                self .viewport ().update ()

            anim .valueChanged .connect (_on_val )

        anim =self ._lg_reveal_anim 
        try :
            anim .stop ()
        except Exception :
            pass 
        self ._lg_reveal_t =0.0 
        anim .setStartValue (0.0 )
        anim .setEndValue (1.0 )
        anim .start ()

    def update_tools (self ,tools ,category ="",search_text ="",batch_keep =False ):


        pass 

    def on_fav_clicked (self ,tool ):
        is_fav =not is_tool_favorited (tool )
        if is_fav :
            add_favorite_tool (tool )
        else :
            remove_favorite_tool (tool )
        self .favorite_changed .emit (tool ,is_fav )

        self .viewport ().update ()

    def get_selected_tools (self ):
        indexes =self .selectedIndexes ()
        tools =[]
        for idx in indexes :
            t =idx .data (Qt .ItemDataRole .UserRole )
            if t :
                tools .append (t )
        return tools 

    def set_display_mode (self ,mode ):


        pass 

    def enable_batch_mode (self ,enable =True ):
        self .show_select_box =enable 
        self .setSelectionMode (QListView .SelectionMode .MultiSelection if enable else QListView .SelectionMode .SingleSelection )
        self .viewport ().update ()

    def adjust_card_size (self ):

        vp =self .viewport ().size ()
        width =vp .width ()
        height =vp .height ()
        spacing =self .spacing ()

        min_card_w =250
        cols =max (2 ,width //(min_card_w +spacing ))
        cols =min (cols ,10 )


        rows =max (2 ,height //85 )
        rows =min (rows ,8 )


        card_width =max (min_card_w ,(width -(cols -1 )*spacing )//cols )


        raw_h =(height -(rows -1 )*spacing )//rows if rows >0 else 160
        card_height =max (75 ,min (85 ,raw_h ))

        self .setGridSize (QSize (card_width ,card_height ))

    def resizeEvent (self ,e ):
        super ().resizeEvent (e )
        self .adjust_card_size ()
        try :
            self ._lg_update_item_reveal_targets ()
        except Exception :
            pass 

    def contextMenuEvent (self ,event ):
        index =self .indexAt (event .pos ())
        if not index .isValid ():
            return 

        tool =index .data (Qt .ItemDataRole .UserRole )


        if SETTINGS .get ("theme")=="liquid_glass":
            menu =LiquidGlassMenu (self )
        else :
            menu =QMenu (self )

        menu .setCursor (Qt .CursorShape .PointingHandCursor )
        act_run =menu .addAction ("运行")
        menu .addSeparator ()
        act_edit =menu .addAction ("编辑")
        act_del =menu .addAction ("删除")
        menu .addSeparator ()
        act_folder =menu .addAction ("打开程序文件夹")
        act_cmd =menu .addAction ("在此处打开CMD")
        act_ps =menu .addAction ("在此处打开PowerShell")


        pos =self .mapToGlobal (event .pos ())

        def _on_triggered (action ):
            try :
                if action ==act_run :
                    self .tool_run .emit (tool )
                elif action ==act_edit :
                    self .tool_edit .emit (tool )
                elif action ==act_del :
                    self .tool_delete .emit (tool )
                elif action in (act_folder ,act_cmd ,act_ps ):
                    self ._handle_context_action (action ,tool ,act_folder ,act_cmd ,act_ps )
            finally :
                try :
                    menu .deleteLater ()
                except Exception :
                    pass 

        menu .triggered .connect (_on_triggered )
        self ._lg_ctx_menu =menu 
        try :
            anim =QVariantAnimation (menu )
            anim .setDuration (140 )
            anim .setEasingCurve (QEasingCurve .Type .OutCubic )
            base_pos =pos 
            lift =8 

            def _on_val (v ):
                t =float (v )
                try :
                    menu .setWindowOpacity (t )
                except Exception :
                    pass 
                try :
                    menu .move (base_pos .x (),base_pos .y ()+int (lift *(1.0 -t )))
                except Exception :
                    pass 

            anim .valueChanged .connect (_on_val )

            def _start_anim ():
                try :
                    menu .setWindowOpacity (0.0 )
                except Exception :
                    return 
                anim .setStartValue (0.0 )
                anim .setEndValue (1.0 )
                anim .start ()

            try :
                menu .aboutToShow .connect (_start_anim )
            except Exception :
                QTimer .singleShot (0 ,_start_anim )
        except Exception :
            pass 
        menu .popup (pos )

    def _handle_context_action (self ,action ,tool ,act_folder ,act_cmd ,act_ps ):
        from utils import SETTINGS 
        from core .env_manager import EnvManager 

        path =tool .get ("path","")
        base_path =os .path .abspath ("tools")
        if not os .path .isabs (path ):
            abs_path =os .path .join (base_path ,path )
        else :
            abs_path =os .path .abspath (path )

        folder_path =""
        if os .path .isfile (abs_path ):
            folder_path =os .path .dirname (abs_path )
        elif os .path .isdir (abs_path ):
            folder_path =abs_path 

        if not folder_path or not os .path .exists (folder_path ):
            return 

        if action ==act_folder :
            if sys .platform .startswith ("win"):
                subprocess .Popen (["explorer",folder_path ])
        elif action ==act_cmd :
            EnvManager ().open_cmd (cwd =folder_path ,env_type ="cli_default")
        elif action ==act_ps :
            EnvManager ().open_powershell (cwd =folder_path ,env_type ="cli_default")


class LiquidGlassMenu (QMenu ):
    def __init__ (self ,parent =None ):
        super ().__init__ (parent )
        self ._lg_hover_action =None 
        self ._lg_hover_t =0.0 
        self ._lg_hover_anim =QVariantAnimation (self )
        self ._lg_hover_anim .setDuration (140 )
        self ._lg_hover_anim .setEasingCurve (QEasingCurve .Type .OutCubic )
        self ._lg_hover_anim .valueChanged .connect (self ._on_anim )
        self .setMouseTracking (True )

    def _on_anim (self ,v ):
        self ._lg_hover_t =float (v )
        self .update ()

    def mouseMoveEvent (self ,e ):
        act =self .actionAt (e .pos ())
        if act !=self ._lg_hover_action :
            self ._lg_hover_action =act 
            try :
                self ._lg_hover_anim .stop ()
            except Exception :
                pass 
            try :
                if act is not None :
                    self ._lg_hover_anim .setDuration (120 )
                else :
                    self ._lg_hover_anim .setDuration (90 )
            except Exception :
                pass 
            self ._lg_hover_anim .setStartValue (float (self ._lg_hover_t or 0.0 ))
            self ._lg_hover_anim .setEndValue (1.0 if act is not None else 0.0 )
            self ._lg_hover_anim .start ()
        super ().mouseMoveEvent (e )

    def leaveEvent (self ,e ):
        self ._lg_hover_action =None 
        try :
            self ._lg_hover_anim .stop ()
        except Exception :
            pass 
        try :
            self ._lg_hover_anim .setDuration (90 )
        except Exception :
            pass 
        self ._lg_hover_anim .setStartValue (self ._lg_hover_t )
        self ._lg_hover_anim .setEndValue (0.0 )
        self ._lg_hover_anim .start ()
        super ().leaveEvent (e )

    def paintEvent (self ,e ):

        if SETTINGS .get ("theme")=="liquid_glass"and self ._lg_hover_action is not None and self ._lg_hover_t >0.0 :
            try :
                r =self .actionGeometry (self ._lg_hover_action )
                if r .isValid ()and r .height ()>0 :
                    p =QPainter (self )
                    p .setRenderHint (QPainter .RenderHint .Antialiasing )
                    p .setPen (Qt .PenStyle .NoPen )
                    a =int (60 *self ._lg_hover_t )
                    p .setBrush (QColor (0 ,122 ,255 ,a ))
                    rr =r .adjusted (6 ,2 ,-6 ,-2 )
                    p .drawRoundedRect (rr ,8 ,8 )
            except Exception :
                pass 
        super ().paintEvent (e )
