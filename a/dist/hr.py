import os
import tkinter as tk
# 主程序开始
opened = []
closed = []
Gn = {}  # 用来存储状态和对应的深度，也就是初始结点到当前结点的路径长度
Fn = {}  # 用来存放状态对应的估价函数值
parent = {}  # 用来存储状态对应的父结点

# expand中存储的是九宫格中每个位置对应的可以移动的情况
# 当定位了0的位置就可以得知可以移动的情况
expand = {0: [1, 3], 1: [0, 2, 4], 2: [1, 5],
            3: [0, 4, 6], 4: [3, 1, 5, 7], 5: [4, 2, 8],
            6: [3, 7], 7: [6, 4, 8], 8: [7, 5]}

def THEnum(node):
    Sum = 0
    for i in range(1, 9):
        num = 0
        for j in range(0, i):
            if node[j] > node[i] and node[i] != '0':
                num = num + 1
        Sum += num
    return Sum


# h(n)函数，用于计算估价函数f(n)，这里的h(n)选择的是与目标相比错位的数目
def Hn(node):
    global goal
    hn = 0
    for i in range(0, 9):
        if node[i] != goal[i]:
            hn += 1
    return hn


# 拓展node状态对应的子结点
def Expand(node):
    global expand
    tnode = []
    state = node.index("0")
    elist = expand[state]
    j = state
    for i in elist:
        j = state
        if i > j:
            i, j = j, i
        re = node[:i] + node[j] + node[i + 1:j] + node[i] + node[j + 1:]
        tnode.append(re)
    return tnode


# 将最后的结果按格式输出
def PRINT(result):
    f = open('hrout.txt', 'w')
    for i in range(len(result)):
        print("step--" + str(i + 1), file=f)
        print(result[i][:3], file=f)
        print(result[i][3:6], file=f)
        print(result[i][6:], file=f)


# 选择opened表中的最小的估价函数值对应的状态
def MIN(opened):
    ll = {}
    for node in opened:
        k = Fn[node]
        ll[node] = k
    kk = min(ll, key=ll.get)
    return kk

def click_1():
    global start, goal
    start = En1.get()
    goal = En2.get()
    if start == goal:
        print("初始状态和目标状态一致！")
    # 判断从初始状态是否可以达到目标状态
    if (THEnum(start) % 2) != (THEnum(goal) % 2):
        print("该目标状态不可达！")
    else:
        parent[start] = -1  # 初始结点的父结点存储为-1
        Gn[start] = 0  # 初始结点的g(n)为0
        Fn[start] = Gn[start] + Hn(start)  # 计算初始结点的估价函数值

        opened.append(start)  # 将初始结点存入opened表
        while opened:
            current = MIN(opened)  # 选择估价函数值最小的状态
            del Fn[current]
            opened.remove(current)  # 将要遍历的结点取出opened表

            if current == goal:
                break
            if current not in closed:
                closed.append(current)  # 存入closed表
                Tnode = Expand(current)  # 扩展子结点
                for node in Tnode:
                    # 如果子结点在opened和closed表中都未出现，则存入opened表
                    # 并求出对应的估价函数值
                    if node not in opened and node not in closed:
                        Gn[node] = Gn[current] + 1
                        Fn[node] = Gn[node] + Hn(node)
                        parent[node] = current
                        opened.append(node)
                    else:
                        # 若子结点已经在opened表中，则判断估价函数值更小的一个路径
                        # 同时改变parent字典和Fn字典中的值
                        if node in opened:
                            fn = Gn[current] + 1 + Hn(node)
                            if fn < Fn[node]:
                                Fn[node] = fn
                                parent[node] = current

        result = []  # 用来存放路径
        result.append(current)
        while parent[current] != -1:  # 根据parent字典中存储的父结点提取路径中的结点
            current = parent[current]
            result.append(current)
        result.reverse()  # 逆序
        PRINT(result)  # 按格式输出结果

def click_2():
    os.system('python hrstep.py')#C://Users//Lenovo//Desktop//a//solution//hr//hrstep.py

window = tk.Tk()
window.title("欢迎使用华容道/八数码计算器")
window.geometry('510x300')
lab_1 = tk.Label(window, text="请输入初始状态(从左至右，从上到下，如：102345678)：",font=('隶书',15)).grid(row=0,column=1)
En1 = tk.Entry(window)
lab_2 = tk.Label(window, text="请输入目标状态(从左至右，从上到下，如：123456780)：",font=('隶书',15)).grid(row=2,column=1)
En2 = tk.Entry(window)
b1 = tk.Button(window, text = '计算', command=click_1,font=('隶书',15)).grid(row = 4, column=1)
b2 = tk.Button(window, text = '展示解题步骤', command=click_2,font=('隶书',15)).grid(row = 5, column=1)
En1.grid(row=1, column=1, ipady=5)
En2.grid(row=3, column=1, ipady=5)

window.mainloop()