#!/usr/bin/python
# -*- coding: utf-8 -*-
# #  FileName    : main.py
# #  Author      : ShuYu Wang <andelf@gmail.com>
# #  Created     : Mon May  4 13:59:31 2015 by ShuYu Wang
# #  Copyright   : Feather Workshop (c) 2015
# #  Description : MY - Helper
# #  Time-stamp: <2015-05-20 18:11:29 andelf>

import random
import time
import getpass
import optparse
import sys
import os
import shlex
import logging
import logging.handlers
import math
import collections
import socket

from twisted.python.log import PythonLoggingObserver
from twisted.internet import reactor, protocol, defer
from twisted.python import log
from twisted.python.failure import Failure
from twisted.protocols.policies import TimeoutMixin

from vncdotool.client import VNCDoToolFactory, VNCDoToolClient
from vncdotool.loggingproxy import VNCLoggingServerFactory

from vncdotool import rfb

from PIL import Image
import cv2
import numpy as np

import conf


socket.setdefaulttimeout(20.0)



log = logging.getLogger()

SUPPORTED_FORMATS = ('png', 'jpg', 'jpeg', 'gif', 'bmp')


class TimeoutError(RuntimeError):
    pass


def log_exceptions(type_, value, tb):
    log.critical('Unhandled exception:', exc_info=(type_, value, tb))


def log_connected(pcol):
    log.info('connected to %s' % pcol.name)
    return pcol


def error(reason):
    log.critical(reason.getTraceback())
    log.critical(reason.getErrorMessage())
    reactor.exit_status = 10
    reactor.callLater(0.1, reactor.stop)


def stop(pcol):
    reactor.exit_status = 0
    pcol.transport.loseConnection()
    # XXX delay
    reactor.callLater(0.1, reactor.stop)



POSITION = dict(
    task = (1300, 1720),
    package = (270, 1960),
    magic = (836, 1971),
    auto = (123, 1969),
    escape = (138, 1300),
    defence = (130, 1800),
    magic1 = (660, 1272),
    magic2 = (659, 1489),
    magic3 = (671, 1718),
    magic4 = (430, 1270),
    buy = (360, 1600),          # drug store
    buy_add = (716, 1854),
    what_to_do1 = (445, 1730),
    what_to_do3 = (680, 1670),
)


class RECTS(object):
    Tasks = (563, 1544, 748, 421)
    Actions = (202, 1350, 883, 682)
    WindowTitle = (1233, 485, 229, 1080)
    ItemUse = (146, 1486, 640, 540)
    BattleHeading = (1362, 933, 168, 328)
    BottomIcons = (27, 878, 200, 1161)
    TopIcons = (1376, 445, 160, 759)
    LeftIcons = (1044, 10, 332, 184)
    # in battle
    RightIcons = (211, 1858, 865, 200)
    RightTabs = (1182, 1463, 176, 568)
    TaskPopUp = (238, 411, 352, 968)
    AnyPopUp = (498, 519, 540, 1100)

    RightCorner = (1347, 1842, 188, 205)

    RightTeam = (604, 1551, 768, 480)

    ActivityPanelHeader = (981, 215, 143, 1620)
    ActivityPanelButtons = (523, 194, 150, 1670)

    CenterPopUp = (500, 400, 572, 1130)

    YaBiaoRemainTime = (1324, 198, 200, 549)

    BattleTopRightCorner = (1346, 0, 170, 175)

    # 仓库 - 我的包裹
    MyPackage = (329, 1021, 825, 829)

    SanJieQiYuanAnswer = (752, 686, 453, 1239)
    SanJieQiYuanQuestion = (1169, 812, 100, 1050)

class OpenCVImageMatcher(object):
    def __init__(self, img):
        if isinstance(img, Image.Image):
            cv_img = np.array(img)
            self.img = cv2.cvtColor(cv_img, cv2.cv.CV_BGR2RGB)
        else:
            self.img = cv2.imread(imgfile)
        self.img_gray = cv2.cvtColor(self.img, cv2.COLOR_BGR2GRAY)

    def match_sub_image(self, imgfile, threshold = 0.8):
        template = cv2.imread(imgfile, 0)
        res = cv2.matchTemplate(self.img_gray, template, cv2.TM_CCOEFF_NORMED)

        loc = np.where( res >= threshold)

        for x, y in zip(*loc[::-1]):
            return x, y
        return None

    def match_sub_image_in_rect(self, imgfile, rect, threshold = 0.8):

        template = cv2.imread(imgfile, 0)

        # http://stackoverflow.com/questions/19098104/python-opencv2-cv2-wrapper-get-image-size
        height, width = self.img_gray.shape
        # http://stackoverflow.com/questions/15589517/how-to-crop-an-image-in-opencv-using-python
        x, y, w, h = rect
        cropped_img_gray = self.img_gray[y: y + h, x: x + w]

        res = cv2.matchTemplate(cropped_img_gray, template, cv2.TM_CCOEFF_NORMED)
        loc = np.where( res >= threshold)

        locs = zip(*loc[::-1])

        if locs:
            mx, my = locs[0]
            return mx + x, my + y
        return None


    def match_sub_image_multi(self, imgfile, threshold = 0.97):

        template = cv2.imread(imgfile, 0)
        res = cv2.matchTemplate(self.img_gray, template, cv2.TM_CCOEFF_NORMED)

        loc = np.where( res >= threshold)

        return [(x,y) for x, y in zip(*loc[::-1])]


    def is_non_special(self):
        # right corner,
        return self.img[2024, 1530, 0] > 200 and self.img[2024, 1530, 1] > 200 and self.img[2024, 1530, 2] > 200

    def is_battle(self):
        return self.is_non_special() and \
            (not self.match_sub_image_in_rect("./yabiao_remain_time_label.png", RECTS.YaBiaoRemainTime)) and \
            (self.match_sub_image_in_rect("./in_battle_dropdown_button.png", RECTS.BattleTopRightCorner) or \
             self.match_sub_image_in_rect("./battle_cancel_icon.png", RECTS.BottomIcons) or \
             self.match_sub_image_in_rect("./tactical_formation_icon.png", RECTS.BattleHeading) or \
             self.match_sub_image_in_rect("./auto_icon.png", RECTS.BottomIcons))

    def is_normal(self):
        return self.is_non_special() and (
            self.match_sub_image_in_rect("./guide_icon.png", RECTS.TopIcons) or \
            self.match_sub_image_in_rect("./mall_icon.png", RECTS.LeftIcons) or \
            self.match_sub_image_in_rect("./plus_icon.png", RECTS.BottomIcons))



def find_who_is_need_feed(positions):
    need_feed = []
    for x, y in positions:
        if x > 1260 or x < 320:
            # 右上人物血条
            continue
        if y < 255 * x / 263.0 + 71370.0 / 263:
            # 怪物区
            continue
        x -= 120
        y += 20
        need_feed.append((x,y))
    if need_feed:
        need_feed.sort()
        distance = lambda a,b: math.sqrt( (a[0] - b[0])**2 + (a[1] - b[1])**2 )
        need_feed = reduce(lambda acc, p: acc if distance(acc[-1], p) < 30 else acc + [p],
                           need_feed[1:], [need_feed[0]])
        return need_feed
    else:
        return []

class BaseGameLogic(object):
    def __init__(self):
        self.game = None
        self.matcher = None

        self.switch_to = None
        self.STOP_AFTER = 0.5

        self.start_at = time.time()

    def loop(self, game):
        self.game = game
        self.matcher = matcher = OpenCVImageMatcher(game.screen)

        if not matcher.match_sub_image("./login_game_button.png"):
            for y in [40, 80, 536, 939, 1254, 1733, 1908, 2034]:
                r, g, b = game.screen.getpixel((3,y))
                if r > 150:
                    print u"场景过渡： skip"
                    return 0

        if matcher.match_sub_image("./chat_input.png"):
            print u"检测到聊天窗口开启 -- 停止挂机"
            return self.STOP_AFTER

        if matcher.is_battle():
            print u"# 战斗模式"
            self.handle_battle()
        elif matcher.is_normal():
            print u"# 场景模式"
            self.handle_normal()
        else:
            print u"# 特殊模式"
            self.handle_special()

        return self.STOP_AFTER


    def handle_battle(self):
        pass

    def handle_normal(self):
        pass

    def handle_special(self):
        pass

class SanJieQiYuanGameLogic(BaseGameLogic):

    def find_answer_pic_and_click(self, pic):
        pos = self.matcher.match_sub_image_in_rect(pic, RECTS.SanJieQiYuanAnswer)
        if pos:
            self.game.touchAt(*pos)
            return True
        else:
            return False

    def handle_special(self):
        matcher = self.matcher
        if not self.matcher.match_sub_image_in_rect("./sanjieqiyuan_window_title.png", RECTS.WindowTitle):
            return None

        print u"三界奇缘答题"
        if matcher.match_sub_image_in_rect("./sanjieqiyuan/tian_ming_qu_jing_ren.png", RECTS.SanJieQiYuanQuestion):
            print u"寻找3个天命取经人"
            self.find_answer_pic_and_click("./sanjieqiyuan/tang_seng.png") or \
                self.find_answer_pic_and_click("./sanjieqiyuan/sun_wu_kong.png") or \
                self.find_answer_pic_and_click("./sanjieqiyuan/zhu_ba_jie.png")
        elif matcher.match_sub_image_in_rect("./sanjieqiyuan/da_nao_tian_gong.png", RECTS.SanJieQiYuanQuestion):
            print u"谁曾经大闹天宫"
            self.find_answer_pic_and_click("./sanjieqiyuan/sun_wu_kong.png")
        elif matcher.match_sub_image_in_rect("./sanjieqiyuan/sun_wu_kong_shi_fu.png", RECTS.SanJieQiYuanQuestion):
            print u"找出2个孙悟空的师傅"
            self.find_answer_pic_and_click("./sanjieqiyuan/tang_seng.png") or \
                self.find_answer_pic_and_click("./sanjieqiyuan/pu_ti_lao_zu.png")

        elif matcher.match_sub_image_in_rect("./sanjieqiyuan/nv_xing_ke_xuan_jue_se.png", RECTS.SanJieQiYuanQuestion):
            print u"找出3个女性可选角色"
            self.find_answer_pic_and_click("./sanjieqiyuan/wu_man_er.png") or \
                self.find_answer_pic_and_click("./sanjieqiyuan/xuan_cai_e.png") or \
                self.find_answer_pic_and_click("./sanjieqiyuan/gu_jing_ling.png")

        elif matcher.match_sub_image_in_rect("./sanjieqiyuan/niu_mo_wang_yi_jia.png", RECTS.SanJieQiYuanQuestion):
            print u"找出牛魔王一家人"
            self.find_answer_pic_and_click("./sanjieqiyuan/niu_mo_wang.png") or \
                self.find_answer_pic_and_click("./sanjieqiyuan/tie_shan_gong_zhu.png") or \
                self.find_answer_pic_and_click("./sanjieqiyuan/hong_hai_er.png")

        elif matcher.match_sub_image_in_rect("./sanjieqiyuan/xian_zu_zhu_jue.png", RECTS.SanJieQiYuanQuestion):
            print u"找出2个仙族主角"
            self.find_answer_pic_and_click("./sanjieqiyuan/long_tai_zi.png") or \
                self.find_answer_pic_and_click("./sanjieqiyuan/xuan_cai_e.png")

        elif matcher.match_sub_image_in_rect("./sanjieqiyuan/shi_tuo_ling_san_xiong_di.png", RECTS.SanJieQiYuanQuestion):
            print u"找出狮驼岭三兄弟"
            self.find_answer_pic_and_click("./sanjieqiyuan/da_da_wang.png") or \
                self.find_answer_pic_and_click("./sanjieqiyuan/er_da_wang.png") or \
                self.find_answer_pic_and_click("./sanjieqiyuan/san_da_wang.png")

        elif matcher.match_sub_image_in_rect("./sanjieqiyuan/ping_ding_shan_yao_guai.png", RECTS.SanJieQiYuanQuestion):
            print u"找出2个平顶山的妖怪"
            self.find_answer_pic_and_click("./sanjieqiyuan/jin_jiao_da_wang.png") or \
                self.find_answer_pic_and_click("./sanjieqiyuan/yin_jiao_da_wang.png")

        elif matcher.match_sub_image_in_rect("./sanjieqiyuan/jin_chan_zi_zhuan_shi.png", RECTS.SanJieQiYuanQuestion):
            print u"金蝉子转世"
            self.find_answer_pic_and_click("./sanjieqiyuan/tang_seng.png")

        elif matcher.match_sub_image_in_rect("./sanjieqiyuan/jing_jing_gu_niang_xi_huan.png", RECTS.SanJieQiYuanQuestion):
            print u"晶晶姑娘喜欢的人"
            self.find_answer_pic_and_click("./sanjieqiyuan/sun_wu_kong.png")

        elif matcher.match_sub_image_in_rect("./sanjieqiyuan/gu_jing_ling_shi_fu.png", RECTS.SanJieQiYuanQuestion, threshold = 0.9):
            print u"骨精灵的师傅"
            self.find_answer_pic_and_click("./sanjieqiyuan/da_da_wang.png") or \
                self.find_answer_pic_and_click("./sanjieqiyuan/di_zang_wang.png")

        elif matcher.match_sub_image_in_rect("./sanjieqiyuan/shi_tuo_guo_guo_wang.png", RECTS.SanJieQiYuanQuestion):
            print u"狮驼国国王"
            self.find_answer_pic_and_click("./sanjieqiyuan/san_da_wang.png")

        elif matcher.match_sub_image_in_rect("./sanjieqiyuan/kui_mu_lang_ai_ren.png", RECTS.SanJieQiYuanQuestion):
            print u"奎木狼爱人"
            self.find_answer_pic_and_click("./sanjieqiyuan/bai_hua_xiu.png")

        elif matcher.match_sub_image_in_rect("./sanjieqiyuan/long_tai_zi_shi_fu.png", RECTS.SanJieQiYuanQuestion, threshold = 0.9):
            print u"龙太子的师傅"
            self.find_answer_pic_and_click("./sanjieqiyuan/dong_hai_long_wang.png") or \
                self.find_answer_pic_and_click("./sanjieqiyuan/guan_yin.png")

        elif matcher.match_sub_image_in_rect("./sanjieqiyuan/san_ge_gu_gei_le_shei.png", RECTS.SanJieQiYuanQuestion):
            print u"3个箍给了谁"
            self.find_answer_pic_and_click("./sanjieqiyuan/sun_wu_kong.png") or \
                self.find_answer_pic_and_click("./sanjieqiyuan/hong_hai_er.png") or \
                self.find_answer_pic_and_click("./sanjieqiyuan/hei_xiong_jing.png")

        elif matcher.match_sub_image_in_rect("./sanjieqiyuan/yao_chi_zhen_shou.png", RECTS.SanJieQiYuanQuestion):
            print u"瑶池珍兽"
            self.find_answer_pic_and_click("./sanjieqiyuan/fu_rong_xian_zi.png") or \
                self.find_answer_pic_and_click("./sanjieqiyuan/wu_zhong_xian.png") or \
                self.find_answer_pic_and_click("./sanjieqiyuan/hou_xiao_xian.png")

        elif matcher.match_sub_image_in_rect("./sanjieqiyuan/huo_li_da_gong_zhuan_qian.png", RECTS.SanJieQiYuanQuestion):
            print u"消耗活力打工赚钱"
            self.find_answer_pic_and_click("./sanjieqiyuan/yan_ru_yu.png")

        elif matcher.match_sub_image_in_rect("./sanjieqiyuan/san_jie_qi_yuan_finished_label.png", (563, 1011, 147, 603)):
            print u"领取奖励"
            self.game.touchAt(716, 422)
            self.game.touchAt(1319, 1923)
        else:
            print u"不在题库，请手工作答"


class ZhuoGuiGameLogic(BaseGameLogic):
    def __init__(self):
        super(ZhuoGuiGameLogic, self).__init__()

        self.nothing_to_do_counter = 0

    def handle_battle(self):
        print u"判定：战斗中"
        if self.matcher.match_sub_image_in_rect("./fashu_icon.png", RECTS.RightIcons):
            print u"已设置自动战斗！"
            self.game.touchAt(122, 1968)

        pos = self.matcher.match_sub_image_in_rect("./close_icon.png", (818, 1112, 657, 835))
        if pos:
            print u"检测到有窗口遮挡"
            self.game.touchAt(pos[0] + 20, pos[1] + 20)

        # FIXME: not ok
        if False and self.matcher.match_sub_image("./chat_input.png") and False:
            print u"检测到 DEBUG 模式开启"
            self.game.touchAt(1419, 292)
            for c in "test":
                self.game.keyPress(c)
            self.game.touchAt(1420, 940)

        # positions = matcher.match_sub_image_multi("./half_blood.png")
        # need_feed = find_who_is_need_feed(positions)
        # if need_feed:
        #     print u"检测到贫血队员", need_feed

    def handle_normal(self):
        matcher = self.matcher
        game = self.game
        while True:
            pos = matcher.match_sub_image_in_rect("./use_icon.png", RECTS.ItemUse)
            if pos:
                print u"任务道具使用"
                game.touchAt(*pos)
                break

            pos = matcher.match_sub_image_in_rect("./zhuogui_label.png", RECTS.Tasks) or \
                  matcher.match_sub_image_in_rect("./qiannianligui_label.png", RECTS.Tasks)
            if pos:
                print u"追踪当前捉鬼任务"
                game.touchAt(pos[0] + 20, pos[1] + 40)
                break

            pos = matcher.match_sub_image_in_rect("./zhuagui_button.png", RECTS.Actions)
            if pos:
                print u"领取抓鬼任务"
                game.touchAt(*pos)
                break

            if game.status.get("nothing_to_do_counter", 0) >= 2 :
                print u"连续%d尝试失败，尝试打开活动窗口领任务！" % game.nothing_to_do_counter
                game.screen.save("./2.png")

                d = defer.Deferred()
                d.addCallback(lambda _, *args: game.touchAt(*args), 1454, 700)
                d.addCallback(lambda _, *args: game.pause(*args), 0.5)
                print u"切换到日常活动标签"
                d.addCallback(lambda _, *args: game.touchAt(*args), 1194, 351)

                game.deferred = d
                return 1.0
            else:
                self.nothing_to_do_counter += 1
                print u"警告！未发现可用任务，重试！"
                return 1.0      # 直接返回

            # while
            # 归 0
            self.nothing_to_do_counter = 0
            break



    def handle_special(self):
        matcher = self.matcher
        game = self.game
        while True:
            if matcher.match_sub_image_in_rect("./zhuagui_finished_label.png", RECTS.CenterPopUp):
                print u"对话框：检测到询问是否继续捉鬼"
                game.touchAt(640, 1220)
                break

            if matcher.match_sub_image("./login_game_button.png"):
                print u"弹窗：游戏登录窗口"
                game.touchAt(224, 1036)
                STOP_AFTER = 5.0
                break

            if matcher.match_sub_image_in_rect("./activity_label.png", RECTS.WindowTitle):
                print u"弹窗：活动列表"
                print u"尝试领取捉鬼任务"
                #game.touchAt(363, 1658)
                #game.pause(0.5)
                while True:
                    # 活跃度奖励
                    if matcher.match_sub_image("./activity_info_popup_label.png"):
                        print u"BUG: 任务详情页被打开，关闭活动窗口"
                        game.touchAt(1321, 1872)
                        game.touchAt(1321, 1872)
                        break

                    pos = matcher.match_sub_image_in_rect("./activity_zhuogui_label.png", RECTS.ActivityPanelHeader)
                    if pos:
                        game.touchAt(pos[0] - 420, pos[1] + 120)
                        print u"领取捉鬼任务！等待到达..."
                        STOP_AFTER = 5.0
                        break

                    print u"未找到捉鬼任务，尝试滑动下一页..."
                    game.mouseMove(810, 1685)
                    game.mouseDown(1)
                    game.mouseDrag(810, 900, step = 20)
                    game.mouseUp(1)
                    break
            break

        else:
            print u"未知特殊模式，尝试直接点击继续捉鬼按钮位置"
            game.touchAt(640, 1220)



class RoutineWorkGameLogic(BaseGameLogic):
    """日常任务逻辑"""
    def __init__(self):
        super(RoutineWorkGameLogic, self).__init__()

        self.nothing_to_do_counter = 0
        self.ping_ding_an_bang = False


    def handle_battle(self):
        mathcer = self.matcher
        game = self.game
        if matcher.match_sub_image_in_rect("./fashu_icon.png", RECTS.RightIcons):
            print u"已设置自动战斗！"
            game.touchAt(122, 1968)
        pos = matcher.match_sub_image("./close_icon.png")
        if pos:
            print u"检测到有窗口遮挡"
            game.touchAt(pos[0] + 20, pos[1] + 20)

    def handle_normal(self):
        mathcer = self.matcher
        game = self.game
        while True:
            if not self.ping_ding_an_bang:
                # 右上角有小红点，所以要严格匹配
                pos = matcher.match_sub_image_in_rect("./guaji_notify_icon.png", RECTS.TopIcons, threshold = 0.9)
                if pos:
                    print u"挂机图标：领取平定安邦任务"
                    d = defer.Deferred()
                    d.addCallback(lambda _, *arg: game.touchAt(*arg), *pos)
                    d.addCallback(lambda _, *arg: game.pause(*arg), 2.0)
                    # 平定安邦
                    d.addCallback(lambda _, *arg: game.touchAt(*arg), 267, 274)
                    game.deferred = d
                    STOP_AFTER = 5.0
                    game.status['ping_ding_an_bang'] = True
                    break

            pos = matcher.match_sub_image_in_rect("./bangpai_task.png", RECTS.Actions)
            if pos:
                print u"处理帮派任务按钮", pos
                game.touchAt(*pos)
                break

            pos = matcher.match_sub_image_in_rect("./qiecuo_icon.png", RECTS.Actions)
            if pos:
                print u"处理帮派任务--切磋"
                game.touchAt(*pos)
                break

            # 这里的领取宝图任务可能和领取别的任务的描述相似度过高，所以取 t=0.9
            pos = matcher.match_sub_image_in_rect("./lingqu_baotu_button.png", RECTS.Actions, threshold=0.9) or \
                  matcher.match_sub_image_in_rect("./lingqu_baotu_tingtingwufang_button.png", RECTS.Actions)
            if pos:
                print u"领取宝图任务"
                print u"重置藏宝图状态"
                game.status['cang_bao_tu'] = False
                game.touchAt(*pos)
                break

            pos = matcher.match_sub_image_in_rect("./get_bangpai_task_button.png", RECTS.Actions)
            if pos:
                print u"领取帮派任务"
                game.touchAt(*pos)
                break

            pos = matcher.match_sub_image_in_rect("./yasong_putong_biaoyin_button.png", RECTS.Actions)
            if pos:
                print u"领取普通运镖任务"
                game.touchAt(*pos)
                break

            pos = matcher.match_sub_image_in_rect("./shimen_extra_task_button.png", RECTS.Actions)
            if pos:
                print u"特殊师门任务按钮"
                game.touchAt(*pos)
                break

            # 只有一个NPC上有多个任务时候才会出现
            pos = matcher.match_sub_image_in_rect("./shimenrenwu_button.png", RECTS.Actions)
            if pos:
                print u"师门任务按钮"
                game.touchAt(*pos)
                break

            pos = matcher.match_sub_image_in_rect("./use_icon.png", RECTS.ItemUse)
            if pos:
                print u"处理任务道具使用", pos
                game.touchAt(*pos)
                STOP_AFTER = 3.0
                break


            # $$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$
            pt = None

            def match_and_click(pic, description):
                # use RECT match
                pos = matcher.match_sub_image_in_rect(pic, RECTS.Tasks)
                if pos:
                    print u"任务：" + description
                    #pt = pos[0], pos[1] + 150
                    pt = pos[0], 2000 # 尽量点击边界，免得误伤
                    game.pause(0.5)
                    game.touchAt(*pt)
                    game.pause(0.2)
                    game.touchAt(*pt)
                    game.pause(0.2)
                    return True
                return False

            if match_and_click("./xuanwu_label.png", u"帮派玄武任务"):
                pass
            elif match_and_click("./qinglong_label.png", u"帮派青龙任务"):
                pass
            elif match_and_click("./zhuque_label.png", u"帮派朱雀任务"):
                pass
            elif match_and_click("./shimen_label.png", u"师门"):
                pass
            elif match_and_click("./baotu_label.png", u"藏宝图"):
                pass
            # FIXME: 红尘试炼需要多种按钮格式配合 无法处理
            # elif match_and_click("./hongchenshilian_label.png", "红尘试炼"):
            #     pass
            #elif matcher.match_sub_image_in_rect("./team_icon.png", RECTS.RightTabs):
            elif matcher.match_sub_image_in_rect("./team_tab_label.png", RECTS.RightTeam) or \
                 matcher.match_sub_image_in_rect("./team_tab_blood_magic.png", RECTS.RightTeam):
                print u"检测到活动标签为队伍，尝试切换为任务标签"
                game.touchAt(1290, 1732)

            elif not game.status.get("cang_bao_tu", False):
                print u"打开包裹寻找藏宝图"
                game.touchAt(267, 1968)
                game.touchAt(247, 1676)
            else:
                if game.status.get("nothing_to_do_counter", 0) >= 2:
                    print u"尝试打开活动窗口领任务！"
                    game.screen.save("./2.png")

                    d = defer.Deferred()
                    d.addCallback(lambda _, *args: game.touchAt(*args), 1454, 700)
                    d.addCallback(lambda _, *args: game.pause(*args), 0.5)
                    print u"切换到日常活动标签"
                    d.addCallback(lambda _, *args: game.touchAt(*args), 1194, 351)
                    game.deferred = d
                    return 1.0
                else:
                    game.status["nothing_to_do_counter"] = game.status.get("nothing_to_do_counter", 0) + 1
                    print u"警告！未发现可用任务，重试！"
                    return 1.0

            # while
            break
        # 重置 counter
        game.status["nothing_to_do_counter"] = 0




# game is the Game Client
def loop(game):
    width, height = game.width, game.height
    # print '#', time.ctime()

    #matcher = OpenCVImageMacher("./2.png")
    matcher = OpenCVImageMatcher(game.screen)

    STOP_AFTER = 0.5

    ######################################## 过渡
    # 最左边经验条，为橘红色时，场景过渡进度条
    if not matcher.match_sub_image("./login_game_button.png"):
        for y in [40, 80, 536, 939, 1254, 1733, 1908, 2034]:
            r, g, b = game.screen.getpixel((3,y))
            # FIXME
            if r > 150:
                print r, g, b
                print u"场景过渡： skip"
                #reactor.callLater(STOP_AFTER, reactor.stop)
                return 0

    # elif matcher.match_sub_image_in_rect("./kicked_out_label.png", RECTS.AnyPopUp):
    #     print u"警告：帐号被踢出"
    #     return
    ######################################## 战斗
    # 判定自动、取消按钮，阵法图标
    if matcher.is_battle():
        print u"判定：战斗中"
        if matcher.match_sub_image_in_rect("./fashu_icon.png", RECTS.RightIcons):
            print u"已设置自动战斗！"
            game.touchAt(122, 1968)
        pos = matcher.match_sub_image("./close_icon.png")
        if pos:
            print u"检测到有窗口遮挡"
            game.touchAt(pos[0] + 20, pos[1] + 20)

        else:
            # 尝试点一下边界，清理未关闭对话框
            game.touchAt(1483, 601)

    ######################################## 一般场景
    # 判定 “指引”， 加号，商城
    elif matcher.is_normal():
        # 用 while 循环的 break 快速退出判断
        while True:
            print u"判定：一般场景"
            if not game.status.get('ping_ding_an_bang', False):
                pos = matcher.match_sub_image_in_rect("./guaji_notify_icon.png",
                                                      RECTS.TopIcons,
                                                      threshold = 0.9)
                if pos:
                    print u"挂机图标：领取平定安邦任务"
                    d = defer.Deferred()
                    d.addCallback(lambda _, *arg: game.touchAt(*arg), *pos)
                    d.addCallback(lambda _, *arg: game.pause(*arg), 2.0)
                    # 平定安邦
                    d.addCallback(lambda _, *arg: game.touchAt(*arg), 267, 274)
                    game.deferred = d
                    STOP_AFTER = 5.0
                    game.status['ping_ding_an_bang'] = True
                    break

            pos = matcher.match_sub_image_in_rect("./bangpai_task.png", RECTS.Actions)
            if pos:
                print u"处理帮派任务按钮", pos
                game.touchAt(*pos)
                break

            pos = matcher.match_sub_image_in_rect("./qiecuo_icon.png", RECTS.Actions)
            if pos:
                print u"处理帮派任务--切磋"
                game.touchAt(*pos)
                break

            # 这里的领取宝图任务可能和领取别的任务的描述相似度过高，所以取 t=0.9
            pos = matcher.match_sub_image_in_rect("./lingqu_baotu_button.png", RECTS.Actions, threshold=0.9) or \
                  matcher.match_sub_image_in_rect("./lingqu_baotu_tingtingwufang_button.png", RECTS.Actions)
            if pos:
                print u"领取宝图任务"
                print u"重置藏宝图状态"
                game.status['cang_bao_tu'] = False
                game.touchAt(*pos)
                break

            pos = matcher.match_sub_image_in_rect("./get_bangpai_task_button.png", RECTS.Actions)
            if pos:
                print u"领取帮派任务"
                game.touchAt(*pos)
                break

            pos = matcher.match_sub_image_in_rect("./yasong_putong_biaoyin_button.png", RECTS.Actions)
            if pos:
                print u"领取普通运镖任务"
                game.touchAt(*pos)
                break

            pos = matcher.match_sub_image_in_rect("./shimen_extra_task_button.png", RECTS.Actions)
            if pos:
                print u"特殊师门任务按钮"
                game.touchAt(*pos)
                break

            # 只有一个NPC上有多个任务时候才会出现
            pos = matcher.match_sub_image_in_rect("./shimenrenwu_button.png", RECTS.Actions)
            if pos:
                print u"师门任务按钮"
                game.touchAt(*pos)
                break

            pos = matcher.match_sub_image_in_rect("./use_icon.png", RECTS.ItemUse)
            if pos:
                print u"处理任务道具使用", pos
                game.touchAt(*pos)
                if matcher.match_sub_image_in_rect("./cangbaotu_icon.png", RECTS.ItemUse):
                    STOP_AFTER = 10.0
                    print u"藏宝图使用"
                else:
                    STOP_AFTER = 3.0
                break


            # $$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$
            pt = None

            def match_and_click(pic, description):
                # use RECT match
                pos = matcher.match_sub_image_in_rect(pic, RECTS.Tasks)
                if pos:
                    print u"任务：" + description
                    #pt = pos[0], pos[1] + 150
                    pt = pos[0], 2000 # 尽量点击边界，免得误伤
                    game.pause(0.5)
                    game.touchAt(*pt)
                    game.pause(0.2)
                    game.touchAt(*pt)
                    game.pause(0.2)
                    return True
                return False

            if match_and_click("./xuanwu_label.png", u"帮派玄武任务"):
                pass
            elif match_and_click("./qinglong_label.png", u"帮派青龙任务"):
                pass
            elif match_and_click("./zhuque_label.png", u"帮派朱雀任务"):
                pass
            elif match_and_click("./shimen_label.png", u"师门"):
                pass
            elif match_and_click("./baotu_label.png", u"藏宝图"):
                pass
            # FIXME: 红尘试炼需要多种按钮格式配合 无法处理
            # elif match_and_click("./hongchenshilian_label.png", "红尘试炼"):
            #     pass
            #elif matcher.match_sub_image_in_rect("./team_icon.png", RECTS.RightTabs):
            elif matcher.match_sub_image_in_rect("./team_tab_label.png", RECTS.RightTeam) or \
                 matcher.match_sub_image_in_rect("./team_tab_blood_magic.png", RECTS.RightTeam):
                print u"检测到活动标签为队伍，尝试切换为任务标签"
                game.touchAt(1290, 1732)

            elif not game.status.get("cang_bao_tu", False):
                print u"打开包裹寻找藏宝图"
                game.touchAt(267, 1968)
                game.touchAt(247, 1676)
            else:
                if game.status.get("nothing_to_do_counter", 0) >= 2:
                    print u"尝试打开活动窗口领任务！"
                    game.screen.save("./2.png")

                    d = defer.Deferred()
                    d.addCallback(lambda _, *args: game.touchAt(*args), 1454, 700)
                    d.addCallback(lambda _, *args: game.pause(*args), 0.5)
                    print u"切换到日常活动标签"
                    d.addCallback(lambda _, *args: game.touchAt(*args), 1194, 351)
                    game.deferred = d
                    return 1.0
                else:
                    game.status["nothing_to_do_counter"] = game.status.get("nothing_to_do_counter", 0) + 1
                    print u"警告！未发现可用任务，重试！"
                    return 1.0

            # while
            break
        # 重置 counter
        game.status["nothing_to_do_counter"] = 0
    else:
        print u"判定：特殊场景"
        pos = matcher.match_sub_image_in_rect("./hand_in_button.png", RECTS.TaskPopUp)
        if pos:
            print u"弹窗：任务物品上交"
            game.touchAt(*pos)
        elif matcher.match_sub_image_in_rect("./shimen_finished_label.png", RECTS.CenterPopUp):
            print u"弹窗：师门结束提示"
            game.touchAt(640, 800)
        elif matcher.match_sub_image_in_rect("./sanjieqiyuan_label.png", RECTS.CenterPopUp):
            print u"弹窗：三界奇缘活动提示"
            print u"忽略此活动"
            game.touchAt(650, 829)
        elif matcher.match_sub_image_in_rect("./kejuxiangshi_label.png", RECTS.CenterPopUp):
            print u"弹窗：科举活动提示"
            print u"忽略此活动"
            game.touchAt(650, 829)

        elif matcher.match_sub_image_in_rect("./yabiao_popup_label.png", RECTS.CenterPopUp):
            print u"弹窗：押镖确认询问"
            game.touchAt(667, 1218)

        elif matcher.match_sub_image_in_rect("./drug_store_icon.png", RECTS.WindowTitle):
            print u"弹窗：药店购买"
            for i in range(14):
                game.touchAt(*POSITION["buy_add"])
            game.touchAt(*POSITION["buy"])
            print u"购买 15 个完成"

        elif matcher.match_sub_image_in_rect("./shanghui_label.png", RECTS.WindowTitle):
            print u"弹窗：商会购买"
            game.touchAt(270, 1603)
            print u"购买完成"
            game.pause(0.2)

        elif matcher.match_sub_image_in_rect("./buy_pet_label.png", RECTS.WindowTitle):
            print u"弹窗：宠物购买"
            pos = matcher.match_sub_image("./buy_button.png")
            game.touchAt(*pos)
            game.pause(0.5)

        elif matcher.match_sub_image_in_rect("./baitan_label.png", RECTS.WindowTitle):
            print u"弹窗：任务物品摆摊购买"
            # 第二个
            game.touchAt(1023, 1468)
            game.pause(0.5)
            game.touchAt(264, 1583)
            game.pause(0.5)
            game.touchAt(1324, 1852)
        elif matcher.match_sub_image_in_rect("./bingqipu_label.png", RECTS.WindowTitle):
            print u"弹窗：任务物品兵器铺"
            game.touchAt(363, 1658)

        elif matcher.match_sub_image_in_rect("./announcement_label.png", RECTS.WindowTitle):
            print u"弹窗：公告"
            pos = matcher.match_sub_image("./ok_button.png")
            if pos:
                game.touchAt(pos[0] + 40, pos[1] + 40)

        elif not game.status.get('cang_bao_tu', False) and \
             matcher.match_sub_image_in_rect("./package_label.png", RECTS.WindowTitle):
            print u"弹窗：包裹"
            pos = matcher.match_sub_image_in_rect("./cangbaotu_icon.png", RECTS.MyPackage)
            if pos:
                print u"发现藏宝图"
                game.touchAt(*pos)
                print u"使用"
                game.touchAt(608, 788)
                STOP_AFTER = 10.0
            else:
                print u"未找到藏宝图，藏宝图标记完成"
                game.status['cang_bao_tu'] = True

        elif matcher.match_sub_image_in_rect("./lucky_draw.png", RECTS.CenterPopUp):
            print u"弹窗：抽奖转盘"
            game.touchAt(915, 1017)
        elif matcher.match_sub_image_in_rect("./activity_label.png", RECTS.WindowTitle):
            print u"弹窗：活动列表"
            print u"尝试领取任务"
            #game.touchAt(363, 1658)
            #game.pause(0.5)
            while True:
                # 活跃度奖励
                if matcher.match_sub_image("./activity_info_popup_label.png"):
                    print u"BUG: 任务详情页被打开，关闭活动窗口"
                    game.touchAt(1321, 1872)
                    game.touchAt(1321, 1872)
                    break

                pos = matcher.match_sub_image_in_rect("./activity_bangpai_label.png", RECTS.ActivityPanelHeader)
                # 判断是否帮派任务已经做完
                if pos and not matcher.match_sub_image_in_rect("./activity_finished_button.png",
                                                               (pos[0] - 486, pos[1] - 130, 597, 450)):
                    game.touchAt(pos[0] - 420, pos[1] + 120)
                    print u"领取帮派任务！等待到达..."
                    STOP_AFTER = 5.0
                    break

                pos = matcher.match_sub_image_in_rect("./activity_yunbiao_label.png", RECTS.ActivityPanelHeader)
                if pos:
                    # 判定活跃条颜色
                    r, g, b = game.screen.getpixel((279, 1056))
                    if g > 2 * r + 2 * b and not \
                       matcher.match_sub_image_in_rect("./activity_finished_button.png",
                                                       (pos[0] - 486, pos[1] - 130, 597, 450)):
                        game.touchAt(pos[0] - 420, pos[1] + 120)
                        print u"领取运镖任务！等待到达..."
                        STOP_AFTER = 5.0
                        break
                    else:

                        print u"忽略运镖任务"
                        pass
                pos = matcher.match_sub_image_in_rect("./activity_baotu_label.png", RECTS.ActivityPanelHeader)
                if pos and not matcher.match_sub_image_in_rect("./activity_finished_button.png",
                                                               (pos[0] - 486, pos[1] - 130, 597, 450)):
                    game.touchAt(pos[0] - 420, pos[1] + 120)
                    print u"领取宝图任务！等待到达..."
                    STOP_AFTER = 10.0
                    break

                if matcher.match_sub_image_in_rect("./activity_finished_button.png", RECTS.ActivityPanelButtons):
                    game.touchAt(1321, 1872)
                    print u"翻页已达最后，无可用任务，请手动处理！！"
                    game.status['finished'] = True
                else:
                    print u"未找到可用任务，尝试滑动下一页..."
                    #game.touchAt(1192, 361) # 点击日常活动按钮, 已在打开逻辑中处理
                    time.sleep(2.0)
                    # 开始滑动
                    game.mouseMove(810, 1685)
                    game.mouseDown(1)
                    game.mouseDrag(810, 1200, step = 40)
                    game.mouseUp(1)
                    STOP_AFTER = 3.0

                # pos = matcher.match_sub_image_in_rect("./activity_baotu_label.png",
                #                                       RECTS.ActivityPanelHeader)
                # if pos:
                #     game.touchAt(pos[0] - 420, pos[1] + 120)

                #     print u"领取宝图任务！等待到达..."
                #     STOP_AFTER = 10.0
                # else:
                #     print u"未找到可用任务，尝试滑动下一页..."
                #     game.mouseMove(810, 1685)
                #     game.mouseDrag(785, 327, step = 10)

                #     print u"！！！无可玩任务！！！"
                break

        elif matcher.match_sub_image_in_rect("./yabiao_remain_time_label.png", RECTS.YaBiaoRemainTime):
            print u"押镖中，等待完成..."
            STOP_AFTER = 10.0
        elif matcher.match_sub_image("./login_game_button.png"):
            print u"弹窗：游戏登录窗口"
            game.touchAt(224, 1036)

        elif matcher.match_sub_image_in_rect("./continue_icon.png", RECTS.RightCorner):
            print u"剧情：检测到继续按钮"
            game.touchAt(1427, 1983)
            game.touchAt(1427, 1983)
        elif matcher.match_sub_image_in_rect("./daily_checkin_label.png", RECTS.WindowTitle):
            print u"弹窗：每日签到"
            positions = [(1014, 555), (1015, 804), (1003, 1020), (997, 1252), (1003, 1475)]
            for pt in positions:
                game.touchAt(*pt)

            # 关闭
            game.touchAt(1245, 1655)
        else:
            while True:
                pos = matcher.match_sub_image("./close_icon.png")
                if pos:
                    print u"检测到有窗口遮挡"
                    game.touchAt(pos[0] + 20, pos[1] + 20)
                    return 0.5
                else:
                    print u"尝试等待"
                    return 1.0


    return STOP_AFTER


# 帐号切换
def loop_SwitchAccount(game):
    width, height = game.width, game.height
    matcher = OpenCVImageMatcher(game.screen)

    STOP_AFTER = 1.0

    # 第二步， 点击更换帐号 v1.18.0  已废弃
    # if game.status.get("switch_account_stage", 0) == 2:
    #     game.touchAt(688, 906)
    #     game.status["switch_account_stage"] = 3
    #     return 0.1

    # 第三步，登录窗口，点击网易通行证按钮
    if game.status.get("switch_account_stage", 0) == 3:
        print u"登录框：选择使用其他帐号登录"
        d = defer.Deferred()
        # 无关位置
        d.addCallback(lambda _, *arg: game.touchAt(*arg), 1020, 939)
        d.addCallback(lambda _, *arg: game.pause(*arg), 1.0)
        # 网易通行证 icon 按钮
        d.addCallback(lambda _, *arg: game.touchAt(*arg), 542, 787)
        # game.touchAt(1020, 939)
        # game.touchAt(542, 787)
        game.deferred = d

        game.status["switch_account_stage"] = 4
        return 5.0

    # 第四步，帐号密码窗口
    elif game.status.get("switch_account_stage", 0) == 4:

        d = defer.Deferred()
        # 输入窗口
        d.addCallback(lambda _, *arg: game.touchAt(*arg), 897, 895)

        # 等待键盘弹出
        d.addCallback(lambda _, *arg: game.pause(*arg), 1.0)

        # FIXME: 循环中使用 Python 闭包错误
        for c in random.choice(["username"]):
            d.addCallback(lambda _, *arg: game.keyPress(*arg), c)
            d.addCallback(lambda _, *arg: game.pause(*arg), 0.1)
        d.addCallback(lambda *_: game.keyEvent(rfb.KEY_ShiftLeft, down=1))
        d.addCallback(lambda _, *arg: game.keyPress(*arg), "2")
        d.addCallback(lambda _, *arg: game.pause(*arg), 0.1)
        d.addCallback(lambda *_: game.keyEvent(rfb.KEY_ShiftLeft, down=0))

        for c in "163.com":
            d.addCallback(lambda _, *arg: game.keyPress(*arg), c)
            d.addCallback(lambda _, *arg: game.pause(*arg), 0.1)


        d.addCallback(lambda *_: game.keyEvent(rfb.KEY_Tab, down=1))
        d.addCallback(lambda *_: game.keyEvent(rfb.KEY_Tab, down=0))

        for c in "passwd":
            d.addCallback(lambda _, *arg: game.keyPress(*arg), c)
            d.addCallback(lambda _, *arg: game.pause(*arg), 0.1)

        game.deferred = d
        game.status["switch_account_stage"] = 5
        return 0.1

    # 等待输入完成
    elif game.status.get("switch_account_stage", 0) == 5:
        # game.touchAt(818, 962)
        game.status["switch_account_stage"] = 6
        print u"等待输入完成"
        return 5.0

    # 点击确认
    elif game.status.get("switch_account_stage", 0) == 6:
        game.touchAt(722, 1020)
        print u"确认登录"
        game.status["switch_account_stage"] = 7
        return 10.0

    elif game.status.get("switch_account_stage", 0) == 7:
        if matcher.match_sub_image_in_rect("./login_game_button.png", (81, 573, 445, 876)) and not \
           matcher.match_sub_image_in_rect("./server_not_yet_selected_label.png", (81, 573, 445, 876)):
            print u"弹窗：游戏登录窗口"
            game.touchAt(224, 1036)
            game.pause(1.0)
            game.status["finished"] = True
            return 5.0


    ######################################## 过渡
    # 最左边经验条，为橘红色时，场景过渡进度条
    if not matcher.match_sub_image("./login_game_button.png"):
        for y in [40, 80, 536, 939, 1254, 1733, 1908, 2034]:
            r, g, b = game.screen.getpixel((3,y))
            # FIXME
            if r > 150:
                print u"场景过渡： skip"
                return 0

    # elif matcher.match_sub_image_in_rect("./kicked_out_label.png", RECTS.AnyPopUp):
    #     print u"警告：帐号被踢出"
    #     return
    ######################################## 战斗
    # 判定自动、取消按钮，阵法图标
    if matcher.is_battle():
        print u"判定：战斗中"
        return 10

    # 点击加号，然后系统设置，
    elif matcher.is_normal():
        if matcher.match_sub_image_in_rect("./plus_icon.png", RECTS.BottomIcons):
            # 点击右下角 plus icon
            game.touchAt(103, 1966)

            d = defer.Deferred()
            # FIXME: 循环中使用 Python 闭包错误
            d.addCallback(lambda _, *arg: game.pause(*arg), 2.0)
            # 设置位置
            d.addCallback(lambda _, *arg: game.touchAt(*arg), 107, 1117)

            game.deferred = d

            return 4.0
        pos = matcher.match_sub_image_in_rect("./system_icon.png", RECTS.BottomIcons)
        if pos:
            game.touchAt(pos[0] + 40, pos[1] + 40)
            return 0.5

        # 用 while 循环的 break 快速退出判断

    else:
        if matcher.match_sub_image_in_rect("./basic_config_label.png", (1169, 814, 143, 368)):
            print u"窗口：基础设置"
            game.touchAt(380, 725) # 切换帐号
            d = defer.Deferred()
            d.addCallback(lambda _, *arg: game.pause(*arg), 1.0)
            # 确定登出
            d.addCallback(lambda _, *arg: game.touchAt(*arg), 672, 1218)
            d.addCallback(lambda _, *arg: game.pause(*arg), 3.0)
            game.deferred = d

            game.status["switch_account_stage"] = 3 # 帐号信息窗口
            return 4.0

        pos = matcher.match_sub_image("./close_icon.png")
        if pos:
            print u"检测到有窗口遮挡"
            game.touchAt(pos[0] + 20, pos[1] + 20)
        else:
            print u"尝试等待"



class JuQingGameLogic(BaseGameLogic):
    def handle_battle(self):
        matcher = self.matcher
        game = self.game
        if matcher.match_sub_image_in_rect("./fashu_icon.png", RECTS.RightIcons):
            print u"已设置自动战斗！"
            game.touchAt(122, 1968)
            game.pause(0.5)

    def handle_normal(self):
        matcher = self.matcher
        game = self.game
        pos = matcher.match_sub_image_in_rect("./use_icon.png", RECTS.ItemUse)
        if pos:
            print u"任务道具使用", pos
            game.touchAt(*pos)
            game.touchAt(*pos)

        else:
            pos = matcher.match_sub_image_in_rect("./select_pet_label.png", (1009, 609, 264, 837))
            if pos:
                print u"选择宠物"
                game.touchAt(752, 946)
                return

            pos = matcher.match_sub_image_in_rect("./zhuzhan_icon.png", RECTS.BottomIcons)
            if pos:
                print u"设置助战"
                d = defer.Deferred()
                d.addCallback(lambda _, *args: game.touchAt(*args), pos[0] + 40, pos[1] + 40)
                d.addCallback(lambda _, *args: game.pause(*args), 10)

            pos = matcher.match_sub_image_in_rect("./select_what_to_do_label.png", RECTS.Actions)
            if pos:
                print u"选择要做的事"
                game.touchAt(pos[0] - 130, pos[1] + 200)
                game.pause(0.5)
                return

            pos = matcher.match_sub_image_in_rect("./hongchenshilian_label.png", RECTS.Tasks)
            if pos:
                print u"红尘试炼"
                game.touchAt(pos[0] + 20, pos[1] + 200)
                return

            else:
                pt = (1144, 1829)
                pos = matcher.match_sub_image_in_rect("./levelup_needed_label.png", RECTS.Tasks)
                if pos:
                    print u"下一剧情任务等级不够，尝试其他任务"
                    pt = (921, 1887)
                #pt = (750, 1829)
                #
                x, y = pt
                game.touchAt(x, y + 100)

            if matcher.match_sub_image_in_rect("./team_tab_label.png", RECTS.RightTeam) or \
               matcher.match_sub_image_in_rect("./team_tab_blood_magic.png", RECTS.RightTeam):
                print u"检测到活动标签为队伍，尝试切换为任务标签"
                game.touchAt(1290, 1732)

    def handle_special(self):
        matcher = self.matcher
        game = self.game
        pos = matcher.match_sub_image_in_rect("./continue_icon.png", RECTS.RightCorner)
        if pos:
            print u"检测到剧情继续按钮"
            pt = pos[0] + 90, pos[1] + 90
            game.touchAt(*pt)
            game.touchAt(*pt)
            game.touchAt(*pt)
            game.touchAt(*pt)
            game.touchAt(*pt)
            game.touchAt(*pt)
            game.touchAt(*pt)
            return
        pos = matcher.match_sub_image("./buy_button.png")
        if pos:
            print u"买买买"
            game.touchAt(pos[0] + 20, pos[1] + 20)
            return
        pos = matcher.match_sub_image_in_rect("./hand_in_button.png", RECTS.TaskPopUp)
        if pos:
            print u"任务物品上交"
            game.touchAt(*pos)
            return
        else:
            pos = matcher.match_sub_image("./close_icon.png")
            if pos:
                print u"检测到有窗口遮挡"
                game.touchAt(pos[0] + 20, pos[1] + 20)

            else:
                print u"未知特殊模式，尝试随便点点"
                game.touchAt(926, 795)



# def loop_JuQing(game):

#     width, height = game.width, game.height
#     STOP_AFTER = 0.1

#     for y in [40, 80, 536, 939, 1254, 1733, 1908, 2034]:
#         r, g, b = game.screen.getpixel((3,y))
#         # FIXME
#         if r > 150:
#             print u"场景过渡： skip"
#             #reactor.callLater(STOP_AFTER, reactor.stop)
#             return 0

#     matcher = OpenCVImageMatcher(game.screen)
#     # matcher.match_sub_image("./dropdown_button.png")
#     #and not \
#     #   matcher.match_sub_image("./guide_icon.png"):
#     # 战斗取消图标。阵法图标
#     if matcher.is_battle():
#         print u"判定：战斗中"
#         if matcher.match_sub_image("./fashu_icon.png"):
#             print u"已设置自动战斗！"
#             game.touchAt(122, 1968)
#             game.pause(0.5)

#     # 判定 “指引”， 加号
#     elif matcher.is_normal():
#         print u"判定：场景模式"

#         # 无法识别
#         # pos = matcher.match_sub_image("./guide_left_top_border.png")
#         # if pos:
#         #     print u"存在特殊指引"
#         #     game.touchAt(pos[0] - 40, pos[1] + 40)

#         # 任务框
#         pos = matcher.match_sub_image("./use_icon.png")
#         if pos:
#             print u"任务道具使用", pos
#             game.touchAt(*pos)
#             game.touchAt(*pos)
#         else:
#             pos = matcher.match_sub_image("./select_what_to_do_label.png")
#             if pos:
#                 print u"选择要做的事"
#                 game.touchAt(pos[0] - 130, pos[1] + 200)
#                 game.pause(0.5)
#             # pos = matcher.match_sub_image("./action_button_offseted.png")
#             # if pos:
#             #     print u"默认点击按钮"
#             #     game.touchAt(pos[0], pos[1] + 100)
#             #     game.pause(0.5)
#             else:
#                 pt = (1144, 1829)
#                 pos = matcher.match_sub_image_in_rect("./levelup_needed_label.png",
#                                                       RECTS.Tasks)
#                 if pos:
#                     print u"下一剧情任务等级不够，尝试其他任务"
#                     pt = (921, 1887)
#                 #pt = (750, 1829)
#                 #
#                 x, y = pt
#                 game.touchAt(x, y + 100)

#     else:
#         print u"判定：特殊模式"
#         pos = matcher.match_sub_image_in_rect("./continue_icon.png",
#                                               RECTS.RightCorner)
#         if pos:
#             print u"检测到剧情继续按钮"
#             pt = pos[0] + 90, pos[1] + 90
#             game.touchAt(*pt)
#             game.pause(1.0)
#             game.touchAt(*pt)
#             game.pause(1.0)
#             game.touchAt(*pt)
#             game.pause(1.0)
#             game.touchAt(*pt)
#             game.touchAt(*pt)
#             game.touchAt(*pt)
#             game.touchAt(*pt)
#             game.pause(1.0)
#         else:
#             pos = matcher.match_sub_image("./close_icon.png")
#             if pos:
#                 print u"检测到有窗口遮挡"
#                 game.touchAt(pos[0] + 20, pos[1] + 20)

#             else:
#                 print u"未知特殊模式，尝试随便点点"
#                 #game.touchAt(640, 1220)
#                 game.touchAt(926, 795)

#     return STOP_AFTER

class VNCXyqClient(VNCDoToolClient, TimeoutMixin):

    def timeoutConnection(self):
        print "!!!!! 超时！"
        reactor.callLater(0.1, reactor.stop)

        self.transport.abortConnection()


    def vncConnectionMade(self):
        VNCDoToolClient.vncConnectionMade(self)

        self.setTimeout(40)

        self.counter = 0
        self.status = dict()
        self.switching = False

        # self.setPixelFormat(bpp=8, depth=8, bigendian=0, truecolor=1,
        #     redmax=7,   greenmax=7,   bluemax=3,
        #     redshift=5, greenshift=2, blueshift=0
        # )

        #self.status['finished'] = True

        # print dir(self)
        # self.switching = True
        # self.status = {'switch_account_stage': 3}

    def touchAt(self, x, y):
        # 1960, 1260
        x = x + random.randint(-10, 10)
        y = y + random.randint(-10, 20)
        self.mouseMove(x, y)
        self.pause(0.2)
        self.mousePress(1)

    def vncRequestPassword(self):
        if self.factory.password is None:
            #self.factory.password = "123456"
            getpass.getpass('VNC password:')

        self.sendPassword(self.factory.password)

    def d2commitUpdate(self, rectangles):
        VNCDoToolClient.commitUpdate(self, rectangles)

        self.counter += 1
        start_time = time.time()

        #logic = SanJieQiYuanGameLogic()
        logic = JuQingGameLogic()
        sleep_after = logic.loop(self) or 1.0

        print '#', time.ctime(), "tt=%.3fs" % (time.time() - start_time), \
            "wait=%.1fs" % sleep_after, "cnt=%d" % self.counter, self.status

        #reactor.callLater(0.1, reactor.stop)
        reactor.callLater(sleep_after,
                          self.framebufferUpdateRequest,
#                          *RECTS.Tasks,
                          incremental=1)

        self.resetTimeout()
    # looping
    def commitUpdate(self, rectangles):
        self.counter += 1
        start_time = time.time()

        if self.switching:
            if self.status.get('finished', False):
                self.switching = False
                self.status = dict()
                sleep_after = loop(self)
            else:
                print u"切换帐号逻辑！"
                sleep_after = loop_SwitchAccount(self)
        else:
            if self.status.get('finished', False):
                self.switching = True
                print u"启动切换帐号逻辑"
                self.status = dict()
                sleep_after = loop_SwitchAccount(self)
            else:
                sleep_after = loop(self)
        #sleep_after = loop_JuQing(self)

        #sleep_after = loop_ZhuaGui(self)
        sleep_after = sleep_after or 0.1
        print '#', time.ctime(), "tt=%.3fs" % (time.time() - start_time), \
            "wait=%.1fs" % sleep_after, "cnt=%d" % self.counter, self.status

        VNCDoToolClient.commitUpdate(self, rectangles)

        reactor.callLater(sleep_after + 1,
                          self.framebufferUpdateRequest,
                          incremental=1)
        self.resetTimeout()


    def bad_updateRectangle(self, x, y, width, height, data):
        # ignore empty updates
        if not data:
            return

        size = (width, height)
        print len(data), width, height
        update = Image.frombytes('L', size, data, 'raw', 'F;8')
        if not self.screen:
            self.screen = update
        # track upward screen resizes, often occurs during os boot of VMs
        # When the screen is sent in chunks (as observed on VMWare ESXi), the canvas
        # needs to be resized to fit all existing contents and the update.
        elif self.screen.size[0] < (x+width) or self.screen.size[1] < (y+height):
            new_size = (max(x+width, self.screen.size[0]), max(y+height, self.screen.size[1]))
            new_screen = Image.new("RGB", new_size, "black")
            new_screen.paste(self.screen, (0, 0))
            new_screen.paste(update, (x, y))
            self.screen = new_screen
        else:
            self.screen.paste(update, (x, y))

        self.drawCursor()


class ExitingProcess(protocol.ProcessProtocol):

    def processExited(self, reason):
        reactor.callLater(0.1, reactor.stop)

    def errReceived(self, data):
        print data


def build_command_list(factory, args=False, delay=None, warp=1.0):
    client = VNCXyqClient

    if delay:
        delay = float(delay) / 1000.0

    while args:
        cmd = args.pop(0)
        if cmd == 'key':
            key = args.pop(0)
            factory.deferred.addCallback(client.keyPress, key)
        elif cmd in ('kdown', 'keydown'):
            key = args.pop(0)
            factory.deferred.addCallback(client.keyDown, key)
        elif cmd in ('kup', 'keyup'):
            key = args.pop(0)
            factory.deferred.addCallback(client.keyUp, key)
        elif cmd in ('move', 'mousemove'):
            x, y = int(args.pop(0)), int(args.pop(0))
            factory.deferred.addCallback(client.mouseMove, x, y)
        elif cmd == 'click':
            button = int(args.pop(0))
            factory.deferred.addCallback(client.mousePress, button)
        elif cmd in ('mdown', 'mousedown'):
            button = int(args.pop(0))
            factory.deferred.addCallback(client.mouseDown, button)
        elif cmd in ('mup', 'mouseup'):
            button = int(args.pop(0))
            factory.deferred.addCallback(client.mouseUp, button)
        elif cmd == 'type':
            for key in args.pop(0):
                factory.deferred.addCallback(client.keyPress, key)
                if delay:
                    factory.deferred.addCallback(client.pause, delay)
        elif cmd == 'capture':
            filename = args.pop(0)
            imgformat = os.path.splitext(filename)[1][1:]
            if imgformat not in SUPPORTED_FORMATS:
                print 'unsupported image format "%s", choose one of %s' % (
                        imgformat, SUPPORTED_FORMATS)
            else:
                factory.deferred.addCallback(client.captureScreen, filename)
        elif cmd == 'expect':
            filename = args.pop(0)
            rms = int(args.pop(0))
            factory.deferred.addCallback(client.expectScreen, filename, rms)
        elif cmd == 'rcapture':
            filename = args.pop(0)
            x = int(args.pop(0))
            y = int(args.pop(0))
            w = int(args.pop(0))
            h = int(args.pop(0))
            imgformat = os.path.splitext(filename)[1][1:]
            if imgformat not in SUPPORTED_FORMATS:
                print 'unsupported image format "%s", choose one of %s' % (
                        imgformat, SUPPORTED_FORMATS)
            else:
                factory.deferred.addCallback(client.captureRegion, filename, x, y, w, h)
        elif cmd == 'rexpect':
            filename = args.pop(0)
            x = int(args.pop(0))
            y = int(args.pop(0))
            rms = int(args.pop(0))
            factory.deferred.addCallback(client.expectRegion, filename, x, y, rms)
        elif cmd in ('pause', 'sleep'):
            duration = float(args.pop(0)) / warp
            factory.deferred.addCallback(client.pause, duration)
        elif cmd in 'drag':
            x, y = int(args.pop(0)), int(args.pop(0))
            factory.deferred.addCallback(client.mouseDrag, x, y)
        elif os.path.isfile(cmd):
            lex = shlex.shlex(open(cmd), posix=True)
            lex.whitespace_split = True
            args = list(lex) + args
        else:
            print 'unknown cmd "%s"' % cmd

        if delay and args:
            factory.deferred.addCallback(client.pause, delay)


def build_tool():
    factory = VNCDoToolFactory()
    factory.protocol = VNCXyqClient

    factory.deferred.addCallbacks(log_connected)

    args = ["capture", "2.png"]
    build_command_list(factory, args, False, False)

    # 任务
    #factory.deferred.addCallback(loop)
    #factory.deferred.addCallback(loop_ZhuaGui)
    #factory.deferred.addCallback(loop_JuQing)
    factory.deferred.addErrback(error)

    reactor.connectTCP(conf.ip, conf.port, factory)

    reactor.exit_status = 1

    return factory


def setup_logging(logfile=None, verbose=False):
    # route Twisted log messages via stdlib logging
    if logfile:
        handler = logging.handlers.RotatingFileHandler(logfile,
                                                       maxBytes=5*1024*1024, backupCount=5)
        logging.getLogger().addHandler(handler)
        sys.excepthook = log_exceptions

    logging.basicConfig()
    if verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    elif options.verbose:
        logging.getLogger().setLevel(logging.INFO)

    PythonLoggingObserver().start()


def parse_host(server):
    split = server.split(':')

    if not split[0]:
        host = '127.0.0.1'
    else:
        host = split[0]

    if len(split) == 3:  # ::port
        port = int(split[2])
    elif len(split) == 2:  # :display
        port = int(split[1]) + 5900
    else:
        port = 5900

    return host, port


def vncdo():
    setup_logging("./my.log", verbose=True)


    factory = build_tool()
    factory.password = conf.password

    reactor.run()

    sys.exit(reactor.exit_status)


if __name__ == '__main__':
    vncdo()
