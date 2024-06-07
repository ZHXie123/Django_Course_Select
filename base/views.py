from urllib import request
from django.shortcuts import render, HttpResponse, redirect
from PIL import Image, ImageDraw, ImageFont

from io import BytesIO
import random

from django.views import View
import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import MultiLabelBinarizer


from base.predict import randomForest
from base.reg_forms import RegForm
from student import models
from utils.res import ResponseData
from django.http import JsonResponse
from django.contrib import auth
from django.db import transaction
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from collections import Counter


def is_ajax(request):
    return request.headers.get('X-Requested-With') == 'XMLHttpRequest'

def index(request):
    return render(request, 'base/index.html', locals())


def signin(request):
    if is_ajax(request):
        if request.method == 'POST':
            res_dict = ResponseData()
            session_code = request.session.get('auth_code')
            auth_code = request.POST.get('auth_code')
            if auth_code.upper() != session_code.upper():
                res_dict.status = 4000
                res_dict.message = '验证码输入不正确!'
                return JsonResponse(res_dict.get_dict)
            username = request.POST.get('username')
            password = request.POST.get('password')
            user_obj = auth.authenticate(request, username=username, password=password)
            if user_obj:
                auth.login(request, user_obj)
                res_dict.message = '登录成功!'
            else:
                res_dict.status = 4000
                res_dict.message = '用户名或密码输入不正确!'
            return JsonResponse(res_dict.get_dict)
    return render(request, 'base/signin.html')


def signout(request):
    auth.logout(request)
    return redirect('base:index')


def register(request):
    form_obj = RegForm()
    if is_ajax(request):
        if request.method == 'POST':
            res_dict = ResponseData()
            form_obj = RegForm(request.POST)
            if form_obj.is_valid():
                clean_data = form_obj.cleaned_data
                clean_data.pop('confirm_password')
                avatar = request.FILES.get('avatar')
                if avatar:
                    clean_data['avatar'] = avatar
                username = clean_data.get('username')
                try:
                    with transaction.atomic():
                        stu_obj = models.Student.objects.create(name=username)
                        models.UserInfo.objects.create_user(**clean_data, student=stu_obj)
                except Exception as e:
                    print(e)
                    print('服务器错误---register!')
            else:
                error_data = form_obj.errors
                res_dict.status = 4000
                res_dict.message = '数据检验失败!'
                res_dict.data = error_data
            return JsonResponse(res_dict.get_dict)

    return render(request, 'base/register.html', {'form_obj': form_obj})


def get_auth_code(request, size=(450, 35), mode="RGB", bg_color=(255, 255, 255)):
    """ 生成一个图片验证码 """
    _letter_cases = "abcdefghjkmnpqrstuvwxy"  # 小写字母，去除可能干扰的i，l，o，z
    _upper_cases = _letter_cases.upper()  # 大写字母
    _numbers = ''.join(map(str, range(3, 10)))  # 数字
    chars = ''.join((_letter_cases, _upper_cases, _numbers))

    width, height = size  # 宽高
    # 创建图形
    img = Image.new(mode, size, bg_color)
    draw = ImageDraw.Draw(img)  # 创建画笔

    def get_chars():
        """生成给定长度的字符串，返回列表格式"""
        return random.sample(chars, 4)

    def create_lines():
        """绘制干扰线"""
        line_num = random.randint(*(1, 2))  # 干扰线条数

        for i in range(line_num):
            # 起始点
            begin = (random.randint(0, size[0]), random.randint(0, size[1]))
            # 结束点
            end = (random.randint(0, size[0]), random.randint(0, size[1]))
            draw.line([begin, end], fill=(0, 0, 0))

    def create_points():
        """绘制干扰点"""
        chance = min(100, max(0, int(2)))  # 大小限制在[0, 100]

        for w in range(width):
            for h in range(height):
                tmp = random.randint(0, 100)
                if tmp > 100 - chance:
                    draw.point((w, h), fill=(0, 0, 0))

    def create_code():
        """绘制验证码字符"""
        char_list = get_chars()
        code_string = ''.join(char_list)  # 每个字符前后以空格隔开

        for i in range(len(char_list)):
            code_str = char_list[i]
            font = ImageFont.truetype('media/static/font/Rondal-Semibold.ttf', size=24)
            draw.text(((i + 1) * 75, 0), code_str, "red", font=font)

        return code_string

    create_lines()
    create_points()
    code = create_code()
    print(code)

    request.session['auth_code'] = code

    io_obj = BytesIO()
    img.save(io_obj, 'PNG')
    return HttpResponse(io_obj.getvalue())


def edit_avatar(request):
    if request.method == 'POST':
        new_avatar = request.FILES.get('new_avatar')
        if new_avatar:
            request.user.avatar = new_avatar
            request.user.save()
        return redirect('base:index')


def edit_password(request):
    if request.method == 'POST':
        old_password = request.POST.get('old_password')
        new_password = request.POST.get('new_password')
        is_right = request.user.check_password(old_password)
        if is_right:
            request.user.set_password(new_password)
            request.user.save()
            return redirect('base:signin')
        return HttpResponse('原密码错误!')


def students(request):
    student_queryset = models.Student.objects.all()
    paginator = Paginator(student_queryset, 3)  # 每页显示3个学生
    total_pages = paginator.num_pages

    current_page = request.GET.get('page', 1)
    current_page = int(current_page)

    # 验证当前页码是否在有效范围内
    if current_page < 1 or current_page > total_pages:
        current_page = 1

    previous_page = current_page - 1
    next_page = current_page + 1

    # 获取当前页码的学生列表
    stu_list = paginator.get_page(current_page)

    # 计算页码范围
    page_ranges = []
    if current_page > 2:
        page_ranges.append(1)
    if current_page > 1:
        page_ranges.append(current_page - 1)
    page_ranges.append(current_page)
    if current_page < total_pages:
        page_ranges.append(current_page + 1)
    if current_page < total_pages - 1:
        page_ranges.append(total_pages)

    context = {
        'stu_list': stu_list,
        'current_page': current_page,
        'total_pages': total_pages,
        'page_ranges': page_ranges,
        'previous_page': previous_page,
        'next_page': next_page,
    }
    return render(request, 'base/students.html', context)


def classes(request):
    class_queryset = models.Classes.objects.all()
    return render(request, 'base/classes.html', locals())


def course(request):
    course_queryset = models.Course.objects.all()
    return render(request, 'base/course.html', locals())


def teacher(request):
    teacher_queryset = models.Teacher.objects.all()
    return render(request, 'base/teacher.html', locals())

def CanLook(request):
    return render(request,'CanLook.html',locals())

def GetData(request):
    course_queryset = models.Course.objects.all()
    course_names = list(models.Course.objects.all().values_list('name', flat=True))
    class_names = list(models.Classes.objects.all().values_list('name', flat=True))
    course_ids = list(models.Student2Course.objects.all().values_list("course_id",flat=True))
    #print(course_names)
    #print(class_names)
    #热力图数据
    course_student_pairs = list(models.Student2Course.objects.all().values_list("course_id", "student_id", flat=False))
    #print(course_student_pairs)
    # 使用Counter统计每个course_id出现的次数
   # 提取课程ID和学生ID
    course_ids = [pair[0] for pair in course_student_pairs]
    student_ids = [pair[1] for pair in course_student_pairs]

    # 使用 Counter 统计每个课程的选课人数
    course_counts = Counter(course_ids)

    #折线图数据
    courseSelectTime=[]
    courseChineseName = []

    # 输出每个课程的选课人数
    for course_id, count in course_counts.items():
        #print(f"课程 {course_id} 被选了 {count} 次。")
        courseChineseName.append(course_names[course_id-1])
        courseSelectTime.append(count)

    #print(courseChineseName)
    #print(courseSelectTime)


    class_student_pairs = list(models.Student.objects.all().values_list("id", "classes", flat=False))
    #print(class_student_pairs)

    result = []
    #将学号换为班级号，用于统计
    for i in course_student_pairs:
        for j in class_student_pairs:
            if(i[1]==j[0]):
                result.append((i[0],j[1]))
    
    # print(result)
    # print(course_names)
    # print(class_names)

    XData,YData,ResultMap,max = returnHotData(result,course_names,class_names)
    #print(XData)
    # print(YData)
    # print(ResultMap)


    course_id_counts = Counter(course_ids)
    
    # 将统计结果转换为列表或其他所需格式
    course_id_counts_list = list(course_id_counts.items())
    
    courseNameNum = []
    courseNameCount = []
    for i in course_id_counts_list:
        courseNameNum.append(i[0])
        courseNameCount.append(i[1])
    
    courseNameString = []
    for i in courseNameNum:
        courseNameString.append(course_names[i-1])
    
    # 使用列表推导式将courseNameCount和courseNameString转换成所需的格式
    formatted_data = [
    {"value": count, "name": name}
    for count, name in zip(courseNameCount, courseNameString)
    ]
    
    #print(formatted_data)
    #print(course_names)
    #resultForest =  randomForest()

    #print(resultForest)

    

    return JsonResponse({"data":courseNameCount,
                         "courseName":courseNameString,
                         #柱状图
                         
                         #饼图
                         "pieData":formatted_data,
                         #热力图
                         "XData":class_names,
                         "YData":course_names,
                         "resultMap":ResultMap,
                         "max":max,
                         #折线图
                         "courseSelectTime":courseSelectTime,
                         "courseChineseName":courseChineseName},)


def returnHotData(result,course_id,classes_id):
    # 假设course_names和class_names已经按照课程和班级的顺序排序
    course_names = course_id
    class_names = classes_id

    # 初始化一个字典来存储每个课程和班级的选课数量
    course_class_count = {}

    max_enrollment = 0

    

    # 遍历result列表，统计每个课程和班级的选课数量
    for course_id, class_id in result:
        if (course_id, class_id) in course_class_count:
            course_class_count[(course_id, class_id)] += 1
            #记录最大选课数量
            if course_class_count[(course_id, class_id)] > max_enrollment:
                max_enrollment = course_class_count[(course_id, class_id)]
        else:
            course_class_count[(course_id, class_id)] = 1
            

    # 构建热力图的数据
    heatmap_data = []
    for course_name in course_names:
        for class_name in class_names:
            # 假设每个班级和每个课程的组合都存在，如果没有选课则数量为0
            count = course_class_count.get((course_names.index(course_name) + 1, class_names.index(class_name) + 1), 0)
            heatmap_data.append([class_names.index(class_name), course_names.index(course_name), count])

    # 构建x轴和y轴的数据
    x_axis_data = class_id
    y_axis_data = course_id

    # 打印热力图的数据，这里仅作为示例，实际应用中你可能需要转换为JSON或其他格式
    #print("xAxis data:", x_axis_data)
    #print("yAxis data:", y_axis_data)
    #print("Heatmap data:", heatmap_data)

    return x_axis_data,y_axis_data,heatmap_data,max_enrollment


class deepLearning(View):
    def get(self,request):

        class_list = models.Classes.objects.values_list('name', flat=True).distinct()
        class_list = list(class_list)  # 转换为列表
        print(class_list)

        classes = []
        for i in range(len(class_list)):
            classes.append((i+1,class_list[i]))
        print(classes)

        # 定义地区列表
        regions = [
            "北京", "上海", "天津", "重庆",
            "河北", "山西", "辽宁", "吉林", "黑龙江",
            "江苏", "浙江", "安徽", "福建", "江西", "山东", "河南", "湖北", "湖南", "广东", "海南",
            "四川", "贵州", "云南", "陕西", "甘肃", "青海", "内蒙古", "广西", "西藏", "宁夏", "新疆",
            "香港", "澳门"
        ]

        # 创建一个包含 (id, region) 形式的地区列表
        regions_list = [(i+1, region) for i, region in enumerate(regions)]
        print(regions_list)
        
        
        return render(request,'predict.html',locals())
    
    def post(self,request):

        
        age = int(request.POST.get("age"))
        gender = int(request.POST.get("gender"))  # 注意这里的更改
        class_id = int(request.POST.get("class"))
        region = int(request.POST.get("region"))

        print(age, gender, class_id, region)
        

        class_list = models.Classes.objects.values_list('name', flat=True).distinct()
        class_list = list(class_list)  # 转换为列表
        
        try:
            class_index = class_list.index(class_id)
        except ValueError:
            class_index = None  # 或者进行其他错误处理
        

        #读取中文名
        course_names = list(models.Course.objects.all().values_list('name', flat=True))
        #获取序号
        #top_course = randomForest(class_index)
        top_course = randomForest(age,class_id,gender,region)
        
        courseNameResult = []

        top_course = list(set(top_course))

        # 确保top_course中的值不超过course_names的长度
        top_course = [course_id for course_id in top_course if course_id < len(course_names)]

        #将序号转化为中文名
        for i in top_course:
            courseNameResult.append(course_names[i])

        print(courseNameResult)

        ##实现获取序号和老师
        CourseNameAndTeacherId = models.Course.objects.values_list('name',"teacher_id","credit","course_open_time").distinct()
        CourseNameAndTeacherId = list(CourseNameAndTeacherId)
        #print(CourseNameAndTeacherId)

        TeacherName = models.Teacher.objects.values_list('id',"name","phone").distinct()
        TeacherName = list(TeacherName)
        #print(TeacherName)

        CourseNameAndTeacherName = []

        for i in CourseNameAndTeacherId:
            for j in TeacherName:
                if(i[1]==j[0]):
                    CourseNameAndTeacherName.append((i[0],j[1],i[2],i[3],j[2]))

        #print(CourseNameAndTeacherName)

        # 准备一个包含索引和课程教师对的列表
        #print(CourseNameAndTeacherName)

        # 将第一个数组转换成集合，以便于快速查找
        courseNameSet = set(courseNameResult)

        # 遍历包含教师信息的元组列表
        result_with_teacher = [
            course_teacher for course_teacher in CourseNameAndTeacherName 
            if course_teacher[0] in courseNameSet  # 检查课程名称是否在第一个数组中
        ]

        #print(result_with_teacher)

        CourseNameAndTeacherName_with_index = list(enumerate(result_with_teacher,start=1))

        print(CourseNameAndTeacherName_with_index)
        

        

        return render(request,'predict.html',locals())
    

