#!/usr/bin/python
# -*- coding: utf-8 -*-
#!/usr/bin/env python
"""
Command line interface to interact with a VNC Server
(c) 2010 Marc Sibson
MIT License
"""
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

from twisted.python.log import PythonLoggingObserver
from twisted.internet import reactor, protocol
from twisted.python import log
from twisted.python.failure import Failure
from twisted.protocols.policies import TimeoutMixin

from vncdotool.client import VNCDoToolFactory, VNCDoToolClient
from vncdotool.loggingproxy import VNCLoggingServerFactory

from PIL import Image
import cv2
import numpy as np


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


main_image = None


class RECTS(object):
    Tasks = (563, 1544, 748, 421)
    Actions = (202, 1350, 883, 682)
    WindowTitle = (1233, 485, 229, 1080)
    ItemUse = (146, 1486, 640, 540)
    BattleHeading = (1362, 933, 168, 328)
    BottomIcons = (27, 878, 200, 1161)
    TopIcons = (1466, 450, 168, 691)
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

class OpenCVImageMacher(object):
    def __init__(self, imgfile):
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

        threshold = 0.97
        loc = np.where( res >= threshold)

        return [(x,y) for x, y in zip(*loc[::-1])]


def match_sub_image_in_main_image(sub, main):

    img = cv2.imread(main)
    img_gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    template = cv2.imread(sub, 0)
    res = cv2.matchTemplate(img_gray,template,cv2.TM_CCOEFF_NORMED)
    threshold = 0.8
    loc = np.where( res >= threshold)

    for x, y in zip(*loc[::-1]):
        return x, y
    return False

def match_sub_image_in_main_image_multi(sub, main):
    img = cv2.imread(main)
    img_gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    template = cv2.imread(sub, 0)
    res = cv2.matchTemplate(img_gray,template,cv2.TM_CCOEFF_NORMED)
    threshold = 0.97
    loc = np.where( res >= threshold)

    return [(x,y) for x, y in zip(*loc[::-1])]



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




def loop_ZhuaGui(game):
    start_time = time.time()
    # match_sub_image_in_main_image("./dropdown_button.png", "./2.png")
    #and not \
    #   match_sub_image_in_main_image("./guide_icon.png"):
    # 战斗取消图标。阵法图标
    matcher = OpenCVImageMacher("./2.png")

    STOP_AFTER = 0.1
    if matcher.match_sub_image("./chat_input.png"):
        print u"检测到聊天窗口开启 -- 停止挂机"
        reactor.callLater(0.1, reactor.stop)
        return

    if matcher.match_sub_image_in_rect("./in_battle_dropdown_button.png", RECTS.BattleTopRightCorner) or \
       matcher.match_sub_image_in_rect("./battle_cancel_icon.png", RECTS.BottomIcons) or \
       matcher.match_sub_image_in_rect("./tactical_formation_icon.png", RECTS.BattleHeading) or \
       matcher.match_sub_image_in_rect("./auto_icon.png", RECTS.BottomIcons):
        print u"判定：战斗中"
        if matcher.match_sub_image_in_rect("./fashu_icon.png", RECTS.RightIcons):
            print u"已设置自动战斗！"
            game.touchAt(122, 1968)
            game.pause(0.5)
        else:
            # 尝试点一下边界，清理未关闭对话框
            #game.touchAt(1483, 601)
            pass

        pos = matcher.match_sub_image_in_rect("./close_icon.png", (818, 1112, 657, 835))
        if pos:
            print u"检测到有窗口遮挡"
            game.touchAt(pos[0] + 20, pos[1] + 20)

        # FIXME: not ok
        if False and matcher.match_sub_image("./chat_input.png") and False:
            print u"检测到 DEBUG 模式开启"
            game.touchAt(1419, 292)
            game.pause(2.0)
            for c in "test":
                game.keyPress(c)
                game.pause(0.5)
            game.pause(5.0)
            game.touchAt(1420, 940)
            game.pause(0.5)

        # positions = matcher.match_sub_image_multi("./half_blood.png")
        # need_feed = find_who_is_need_feed(positions)
        # if need_feed:
        #     print u"检测到贫血队员", need_feed

    # 判定 “指引”， 加号
    elif matcher.match_sub_image_in_rect("./guide_icon.png", RECTS.TopIcons) or \
         matcher.match_sub_image_in_rect("./mall_icon.png", RECTS.LeftIcons) or \
         matcher.match_sub_image_in_rect("./plus_icon.png", RECTS.BottomIcons):
        print u"判定：场景模式"
        # 任务框
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

            print u"复杂操作开始。尝试领取"
            game.touchAt(1454, 700)
            break
    else:
        print u"判定：特殊模式"
        while True:
            if matcher.match_sub_image_in_rect("./zhuagui_finished_label.png", RECTS.CenterPopUp):
                print u"检测到继续捉鬼弹窗"
                game.touchAt(640, 1220)
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
                    game.mouseDrag(810, 900, step = 40)
                    game.mouseUp(1)
                    break
            break

        else:
            print u"未知特殊模式，尝试识别按钮"
            game.touchAt(640, 1220)
    print "#", time.ctime(), "tt=%.3fs" % (time.time() - start_time)

    reactor.callLater(STOP_AFTER, reactor.stop)



def loop(game):
    width, height = game.width, game.height
    # print '#', time.ctime()

    start_time = time.time()
    matcher = OpenCVImageMacher("./2.png")

    STOP_AFTER = 0.1

    ######################################## 过渡
    # 最左边经验条，为橘红色时，场景过渡进度条
    r, g, b = game.screen.getpixel((3,40))
    if r > 150:
        print u"场景过渡： skip"
        reactor.callLater(STOP_AFTER, reactor.stop)
        return

    # elif matcher.match_sub_image_in_rect("./kicked_out_label.png", RECTS.AnyPopUp):
    #     print u"警告：帐号被踢出"
    #     return
    ######################################## 战斗
    # 判定自动、取消按钮，阵法图标
    elif matcher.match_sub_image_in_rect("./in_battle_dropdown_button.png", RECTS.BattleTopRightCorner) or \
         matcher.match_sub_image_in_rect("./battle_cancel_icon.png", RECTS.BottomIcons) or \
         matcher.match_sub_image_in_rect("./tactical_formation_icon.png", RECTS.BattleHeading) or \
         matcher.match_sub_image_in_rect("./auto_icon.png", RECTS.BottomIcons):
        print u"判定：战斗/押镖中"
        if matcher.match_sub_image_in_rect("./fashu_icon.png", RECTS.RightIcons):
            print u"已设置自动战斗！"
            game.touchAt(122, 1968)
            game.pause(0.5)
        else:
            # 尝试点一下边界，清理未关闭对话框
            game.touchAt(1483, 601)

    ######################################## 一般场景
    # 判定 “指引”， 加号，商城
    elif matcher.match_sub_image_in_rect("./guide_icon.png", RECTS.TopIcons) or \
         matcher.match_sub_image_in_rect("./mall_icon.png", RECTS.LeftIcons) or \
         matcher.match_sub_image_in_rect("./plus_icon.png", RECTS.BottomIcons):

        # 用 while 循环的 break 快速退出判断
        while True:
            print u"判定：一般场景"
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

            pos = matcher.match_sub_image_in_rect("./lingqu_baotu_button.png", RECTS.Actions) or \
                  matcher.match_sub_image_in_rect("./lingqu_baotu_tingtingwufang_button.png", RECTS.Actions)
            if pos:
                print u"领取宝图任务"
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

            pos = matcher.match_sub_image_in_rect("./use_icon.png", RECTS.ItemUse)
            if pos:
                print u"处理任务道具使用", pos
                game.touchAt(*pos)
                game.pause(2)
                break

            # $$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$
            pt = None

            def match_and_click(pic, description):
                # use RECT match
                pos = matcher.match_sub_image_in_rect(pic, RECTS.Tasks)
                if pos:
                    print "任务：" + description
                    pt = pos[0], pos[1] + 150
                    game.pause(0.5)
                    game.touchAt(*pt)
                    game.pause(0.2)
                    game.touchAt(*pt)
                    game.pause(0.2)
                    return True
                return False

            if match_and_click("./xuanwu_label.png", "帮派玄武任务"):
                pass
            elif match_and_click("./qinglong_label.png", "帮派青龙任务"):
                pass
            elif match_and_click("./zhuque_label.png", "帮派朱雀任务"):
                pass
            elif match_and_click("./shimen_label.png", "师门"):
                pass
            elif match_and_click("./baotu_label.png", "藏宝图"):
                pass
            # FIXME: 红尘试炼需要多种按钮格式配合 无法处理
            # elif match_and_click("./hongchenshilian_label.png", "红尘试炼"):
            #     pass
            #elif matcher.match_sub_image_in_rect("./team_icon.png", RECTS.RightTabs):
            elif matcher.match_sub_image_in_rect("./team_tab_label.png", RECTS.RightTeam) or \
                 matcher.match_sub_image_in_rect("./team_tab_blood_magic.png", RECTS.RightTeam):
                print u"检测到活动标签为队伍，尝试切换为任务标签"
                game.touchAt(1290, 1732)

            else:
                print u"警告！！！！未发现可用任务"
                print u"尝试打开活动窗口领任务！"
                game.touchAt(1454, 700)

            # while
            break
    else:
        print u"判定：特殊场景"

        pos = matcher.match_sub_image_in_rect("./hand_in_button.png", RECTS.TaskPopUp)
        if pos:
            print u"弹窗：任务物品上交"
            game.touchAt(*pos)

        elif matcher.match_sub_image_in_rect("./yabiao_popup_label.png", RECTS.CenterPopUp):
            print u"弹窗：押镖确认询问"
            game.touchAt(667, 1218)

        elif matcher.match_sub_image_in_rect("./drug_store_icon.png", RECTS.WindowTitle):
            print u"弹窗：药店购买"
            for i in range(14):
                game.touchAt(*POSITION["buy_add"])
                game.pause(0.2)
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
            game.pause(0.5)

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
                        print u"活跃度不足，忽略运镖任务"
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
                else:
                    print u"未找到可用任务，尝试滑动下一页..."
                    game.mouseMove(810, 1685)
                    game.mouseDown(1)
                    game.mouseDrag(810, 900, step = 40)
                    game.mouseUp(1)

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
            STOP_AFTER = 5.0
        elif matcher.match_sub_image_in_rect("./shimen_finished_label.png", RECTS.CenterPopUp):
            print u"弹窗：师门结束提示"
            game.touchAt(640, 800)
            game.pause(0.5)
        elif matcher.match_sub_image("./login_game_button.png"):
            print u"弹窗：游戏登录窗口"
            game.touchAt(224, 1036)
            game.pause(1.0)

        elif matcher.match_sub_image_in_rect("./continue_icon.png", RECTS.RightCorner):
            print u"剧情：检测到继续按钮"
            game.touchAt(1427, 1983)
            game.pause(1.0)
            game.touchAt(1427, 1983)
            game.pause(1.0)
        else:
            pos = matcher.match_sub_image("./close_icon.png")
            if pos:
                print u"检测到有窗口遮挡"
                game.touchAt(pos[0] + 20, pos[1] + 20)
            else:
                print u"尝试等待"

    if False:
        # 检查指引图标
        if matcher.match_sub_image("./mall_icon.png"):
            print u"判定：场景地图"
            if matcher.match_sub_image("./guaji_icon.png") and False:
                print u"判定：挂机状态处理"
                # 挂机按钮
                game.touchAt(1440, 860)
                game.pause(0.5)
                # 平定安邦
                # print u"尝试领取平定安邦"
                # game.touchAt(280, 270)
                # game.pause(0.5)
                # # 关闭
                # game.touchAt(1317, 12)



        #break
    print '#', time.ctime(), "tt=%.3fs" % (time.time() - start_time)
    reactor.callLater(STOP_AFTER, reactor.stop)




def loop_JuQing(game):
    print "#", time.ctime()

    width, height = game.width, game.height

    r, g, b = game.screen.getpixel((3,40))
    if r > 150:
        print u"判定：场景过渡"
        reactor.callLater(0.1, reactor.stop)
        return

    matcher = OpenCVImageMacher("./2.png")
    # matcher.match_sub_image("./dropdown_button.png")
    #and not \
    #   matcher.match_sub_image("./guide_icon.png"):
    # 战斗取消图标。阵法图标
    if matcher.match_sub_image("./tactical_formation_icon.png") or \
       matcher.match_sub_image("./battle_cancel_icon.png") or \
       matcher.match_sub_image("./auto_icon.png"):
        print u"判定：战斗中"
        if matcher.match_sub_image("./fashu_icon.png"):
            print u"已设置自动战斗！"
            game.touchAt(122, 1968)
            game.pause(0.5)

    # 判定 “指引”， 加号
    elif matcher.match_sub_image("./mall_icon.png") or \
         matcher.match_sub_image("./plus_icon.png"):
        print u"判定：场景模式"

        pos = matcher.match_sub_image("./guide_left_top_border.png")
        if pos:
            print u"存在特殊指引"
            game.touchAt(pos[0] - 40, pos[1] + 40)

        # 任务框
        pos = matcher.match_sub_image("./use_icon.png")
        if pos:
            print u"任务道具使用", pos
            game.touchAt(*pos)
            game.touchAt(*pos)
        else:
            pos = matcher.match_sub_image("./select_what_to_do_label.png")
            if pos:
                print u"选择要做的事"
                game.touchAt(pos[0] - 130, pos[1] + 200)
                game.pause(0.5)
            # pos = matcher.match_sub_image("./action_button_offseted.png")
            # if pos:
            #     print u"默认点击按钮"
            #     game.touchAt(pos[0], pos[1] + 100)
            #     game.pause(0.5)
            else:
                pt = (1144, 1829)
                pos = matcher.match_sub_image_in_rect("./levelup_needed_label.png",
                                                      RECTS.Tasks)
                if pos:
                    print u"下一剧情任务等级不够，尝试其他任务"
                    pt = (921, 1887)
                #pt = (750, 1829)
                #
                x, y = pt
                game.touchAt(x, y + 100)

    else:
        print u"判定：特殊模式"
        pos = matcher.match_sub_image_in_rect("./continue_icon.png",
                                              RECTS.RightCorner)
        if pos:
            print u"检测到剧情继续按钮"
            pt = pos[0] + 90, pos[1] + 90
            game.touchAt(*pt)
            game.pause(1.0)
            game.touchAt(*pt)
            game.pause(1.0)
            game.touchAt(*pt)
            game.pause(1.0)
            game.touchAt(*pt)
            game.touchAt(*pt)
            game.touchAt(*pt)
            game.touchAt(*pt)
            game.pause(1.0)
        else:
            pos = matcher.match_sub_image("./close_icon.png")
            if pos:
                print u"检测到有窗口遮挡"
                game.touchAt(pos[0] + 20, pos[1] + 20)

            else:
                print u"未知特殊模式，尝试随便点点"
                #game.touchAt(640, 1220)
                game.touchAt(926, 795)


    reactor.callLater(0.1, reactor.stop)



class VNCXyqClient(VNCDoToolClient, TimeoutMixin):
    def timeoutConnection(self):
        print "!!!!! 超时！"
        reactor.callLater(0.1, reactor.stop)

        self.transport.abortConnection()


    def vncConnectionMade(self):
        VNCDoToolClient.vncConnectionMade(self)

        self.setTimeout(20)
        # self.setPixelFormat(bpp=8, depth=8, bigendian=0, truecolor=1,
        #     redmax=7,   greenmax=7,   bluemax=3,
        #     redshift=5, greenshift=2, blueshift=0
        # )

        # print dir(self)

    def touchAt(self, x, y):
        # 1960, 1260
        x = x + random.randint(-10, 10)
        y = y + random.randint(-10, 20)
        self.mouseMove(x, y)
        self.pause(0.2)
        self.mousePress(1)

    def vncRequestPassword(self):
        if self.factory.password is None:
            self.factory.password = "123456"
            # getpass.getpass('VNC password:')

        self.sendPassword(self.factory.password)

    # looping
    def commitUpdate(self, rectangles):
        VNCDoToolClient.commitUpdate(self, rectangles)

        print '~ update ~', rectangles
        print self.screen
        self.framebufferUpdateRequest(incremental=1)



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


class VNCDoToolOptionParser(optparse.OptionParser):
    def format_help(self, **kwargs):
        result = optparse.OptionParser.format_help(self, **kwargs)
        result += '\n'.join(
           ['',
            'Commands (CMD):',
            '  key KEY:\tsend KEY to server',
            '\t\tKEY is alphanumeric or a keysym, e.g. ctrl-c, del',
            '  type TEXT:\tsend alphanumeric string of TEXT',
            '  move|mousemove X Y:\tmove the mouse cursor to position X,Y',
            '  click BUTTON:\tsend a mouse BUTTON click',
            '  capture FILE:\tsave current screen as FILE',
            '  expect FILE FUZZ:  Wait until the screen matches FILE',
            '\t\tFUZZ amount of error tolerance (RMSE) in match',
            '  mousedown BUTTON:\tsend BUTTON down',
            '  mouseup BUTTON:\tsend BUTTON up',
            '  pause DURATION:\twait DURATION seconds before sending next',
            '  drag X Y:\tmove the mouse to X,Y in small steps',
            '',
           ])
        return result


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


def build_tool(options, args):
    factory = VNCDoToolFactory()
    factory.protocol = VNCXyqClient

    if options.verbose:
        factory.deferred.addCallbacks(log_connected)

    if args == ['-']:
        lex = shlex.shlex(posix=True)
        lex.whitespace_split = True
        args = list(lex)

    build_command_list(factory, args, options.delay, options.warp)

    # 任务
    factory.deferred.addCallback(loop)
    #factory.deferred.addCallback(loop_ZhuaGui)
    #factory.deferred.addCallback(loop_JuQing)
    factory.deferred.addErrback(error)

    reactor.connectTCP("192.168.1.102", 5900, factory)
    reactor.exit_status = 1

    return factory


def build_proxy(options):
    factory = VNCLoggingServerFactory(options.host, int(options.port))
    port = reactor.listenTCP(options.listen, factory)
    reactor.exit_status = 0
    factory.listen_port = port.getHost().port

    return factory


def add_standard_options(parser):
    parser.disable_interspersed_args()

    parser.add_option('-p', '--password', action='store', metavar='PASSWORD',
        help='use password to access server')

    parser.add_option('-s', '--server', action='store', metavar='SERVER',
        default='127.0.0.1',
        help='connect to VNC server at ADDRESS[:DISPLAY|::PORT] [%default]')

    parser.add_option('--logfile', action='store', metavar='FILE',
        help='output logging information to FILE')

    parser.add_option('-v', '--verbose', action='count',
        help='increase verbosity, use multple times')

    return parser


def setup_logging(options):
    # route Twisted log messages via stdlib logging
    if options.logfile:
        handler = logging.handlers.RotatingFileHandler(options.logfile,
                                      maxBytes=5*1024*1024, backupCount=5)
        logging.getLogger().addHandler(handler)
        sys.excepthook = log_exceptions

    logging.basicConfig()
    if options.verbose > 1:
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


def vnclog():
    usage = '%prog [options] OUTPUT'
    description = 'Capture user interactions with a VNC Server'

    op = optparse.OptionParser(usage=usage, description=description)
    add_standard_options(op)

    op.add_option('--listen', metavar='PORT', type='int',
        help='listen for client connections on PORT [%default]')
    op.set_defaults(listen=5902)

    op.add_option('--forever', action='store_true',
        help='continually accept new connections')

    op.add_option('--viewer', action='store', metavar='CMD',
        help='launch an interactive client using CMD [%default]')

    options, args = op.parse_args()

    setup_logging(options)

    options.host, options.port = parse_host(options.server)

    if len(args) != 1:
        op.error('incorrect number of arguments')
    output = args[0]

    factory = build_proxy(options)

    if options.forever and os.path.isdir(output):
        factory.output = output
    elif options.forever:
        op.error('--forever requires OUTPUT to be a directory')
    elif output == '-':
        factory.output = sys.stdout
    else:
        factory.output = open(output, 'w')

    if options.listen == 0:
        log.info('accepting connections on ::%d', factory.listen_port)

    factory.password = options.password

    if options.viewer:
        cmdline = '%s localhost::%s' % (options.viewer, factory.listen_port)
        proc = reactor.spawnProcess(ExitingProcess(),
                                    options.viewer, cmdline.split(),
                                    env=os.environ)

    reactor.run()

    sys.exit(reactor.exit_status)


def vncdo():
    usage = '%prog [options] (CMD CMDARGS|-|filename)'
    description = 'Command line control of a VNC server'

    op = VNCDoToolOptionParser(usage=usage, description=description)
    add_standard_options(op)

    op.add_option('--delay', action='store', metavar='MILLISECONDS',
        default=os.environ.get('VNCDOTOOL_DELAY', 10), type='int',
        help='delay MILLISECONDS between actions [%defaultms]')

    op.add_option('--force-caps', action='store_true',
        help='for non-compliant servers, send shift-LETTER, ensures capitalization works')

    op.add_option('--localcursor', action='store_true',
        help='mouse pointer drawn client-side, useful when server does not include cursor')

    op.add_option('--nocursor', action='store_true',
        help='no mouse pointer in screen captures')

    op.add_option('-t', '--timeout', action='store', type='int', metavar='TIMEOUT',
        help='abort if unable to complete all actions within TIMEOUT seconds')

    op.add_option('-w', '--warp', action='store', type='float',
        metavar='FACTOR', default=1.0,
        help='pause time is accelerated by FACTOR [x%default]')

    options, args = op.parse_args()

    if not len(args):
        op.error('no command provided')

    setup_logging(options)
    options.host, options.port = parse_host(options.server)

    log.info('connecting to %s:%s', options.host, options.port)

    factory = build_tool(options, args)
    factory.password = options.password

    if options.localcursor:
        factory.pseudocursor = True

    if options.nocursor:
        factory.nocursor = True

    if options.force_caps:
        factory.force_caps = True

    if options.timeout:
        message = 'TIMEOUT Exceeded (%ss)' % options.timeout
        failure = Failure(TimeoutError(message))
        reactor.callLater(options.timeout, error, failure)

    reactor.run()

    sys.exit(reactor.exit_status)


if __name__ == '__main__':
    vncdo()
