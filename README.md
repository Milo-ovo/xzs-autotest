# 学之思开源版（MySQL）自动化测试

针对 [学之思在线考试系统](https://www.mindskip.net/) 开源版的自动化测试套件。
当前以接口测试为主（pytest + requests + Allure），覆盖管理端和学生端核心业务流程，
包含越权、边界、健壮性等非常规场景，后续扩展 UI 自动化。

## 技术栈

- Python 3.10+ / pytest 8
- requests（HTTP 客户端，Cookie 会话持久化）
- pymysql（DB 双重断言：接口返回与数据库记录交叉验证）
- pydantic-settings（`.env` 配置管理）
- allure-pytest（测试报告）
- pytest-rerunfailures（失败重跑，可选）

## 目录结构

```
xzsProject/
├── conftest.py              # pytest 全局钩子：日志、探活、session/学生/越权学生 fixture
├── pytest.ini               # pytest 配置（markers、junitxml）
├── requirements.txt
├── .env.example             # 环境变量模板（复制为 .env 后填实际值）
├── config/
│   └── settings.py          # 配置加载（pydantic-settings）
├── common/
│   ├── request.py           # ApiClient：统一日志、敏感字段打码、Allure 附件
│   ├── response.py          # assert_success / assert_fail 断言工具
│   ├── db.py                # MySQL 查询（单例连接 + atexit 自动关闭）
│   ├── factory.py           # 测试数据工厂：建学科/题/卷/交卷一站式
│   └── utils.py             # unique_suffix / must_find 等工具
├── testcases/               # 70 条用例，19 个文件按模块拆分
│   ├── test_login.py            # 登录成功/失败、登出失效
│   ├── test_login_edge.py       # 登录边界：禁用账号、SQL注入、超长用户名
│   ├── test_subject.py          # 学科 CRUD
│   ├── test_question.py         # 题目（5 种题型参数化 + 必填校验）
│   ├── test_query.py            # 查询筛选：按学科/题型过滤、分页结构
│   ├── test_paper_validation.py # 试卷校验：空卷、重复题、建议时长
│   ├── test_edit_interfaces.py  # 编辑接口回读：改题/卷/任务后详情生效
│   ├── test_exam_full_flow.py   # 学生考试 E2E（含 DB 双重断言）
│   ├── test_exam_rules.py       # 考试规则：重复作答、白卷容错
│   ├── test_scoring.py          # 判分规则：单选/多选/填空对错分
│   ├── test_self_grade_boundary.py # 自评分数上下限边界
│   ├── test_permission.py       # 纵向越权（学生访问管理端 502）+ 数据隔离
│   ├── test_cross_student.py    # 横向越权（P0 安全：学生互看/互改答卷）
│   ├── test_time_window.py      # 时段试卷时间窗：已结束/未开始进入与交卷
│   ├── test_task_isolation.py   # 任务年级隔离：不同年级互不可见
│   ├── test_user_crud.py        # 学生生命周期 + 自助注册 + 资料更新
│   ├── test_pagination_edge.py  # 分页边界：超界、pageSize=0/负/超大不 500
│   ├── test_robustness.py       # 健壮性：非法枚举、操作不存在资源、软删一致性
│   └── test_defects.py          # 已知缺陷回归：重名学科、下拉过滤、必填校验
└── reports/                 # 运行时生成
```

## 快速开始

```powershell
# 1. 建虚拟环境并安装依赖
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

# 2. 复制环境配置并填写
Copy-Item .env.example .env
# 编辑 .env：设置 BASE_URL、账号密码、数据库连接

# 3. 默认 RUN_INTEGRATION=false，只收集不跑（不会误请求服务）
pytest --collect-only

# 4. 确认目标环境就绪后，打开集成开关跑
# 编辑 .env：RUN_INTEGRATION=true
pytest -m smoke          # 只跑冒烟（核心路径，约 10s）
pytest                   # 全量回归
```

## 配置说明（.env）

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `BASE_URL` | `http://localhost:8000` | 后端地址 |
| `RUN_INTEGRATION` | `false` | `false` 时所有真实接口用例被跳过 |
| `ADMIN_USER` / `ADMIN_PASSWORD` | `admin` / `123456` | 管理员账号 |
| `STUDENT_USER` / `STUDENT_PASSWORD` | `student` / `123456` | 学生账号 |
| `DB_HOST` / `DB_PORT` / `DB_NAME` | `localhost` / `3306` / `xzs` | 数据库（用于 DB 双重断言） |
| `REQUEST_TIMEOUT` | `15` | 单请求超时（秒） |

## 生成 Allure 报告

```powershell
pytest --alluredir=reports/allure-results
allure generate reports/allure-results -o reports/allure-report --clean
allure open reports/allure-report
```

## 测试覆盖概览

共 **70 条自动化用例**，覆盖：

- **认证**：登录成功/失败、空值、禁用账号、SQL 注入、超长用户名、登出失效
- **学科**：增删改、重名校验、软删留档、下拉过滤
- **题目**：单选/多选/判断/填空/简答 5 种题型、必填校验、分值边界
- **试卷**：固定卷/时段卷/任务卷、组卷总分、重复题目、建议时长
- **考试 E2E**：任务中心 → 进入试卷 → 作答 → 交卷 → 自动判分 → 自评 → 历史记录（含 DB 断言）
- **判分规则**：单选对错、多选全对/漏选/含错、填空、客观题与主观题分数汇总一致性
- **权限安全**：学生访问管理端被 502 拦截、匿名访问 401、学生间数据隔离、横向越权读/改答卷
- **边界**：分页超界、pageSize=0/负数/超大、时间窗外进入/交卷、自评分数上下限
- **健壮性**：非法枚举值、操作不存在资源、软删一致性

## 已发现缺陷（汇总）

通过本测试套件发现的后端缺陷，已用 `xfail(strict=True)` 固化在测试里——
一旦后端修复，对应用例会变红提醒摘除标记。

### P0 安全漏洞（横向越权）

| 编号 | 问题 |
|------|------|
| D-001 | 学生调 `/student/exampaper/answer/read/{answerId}` 不校验归属，可看任意同学答卷 |
| D-002 | 学生调 `answer/edit` 不校验归属，可改任意同学答卷评分（篡改成绩） |
| D-003 | 学生调 `/student/question/answer/select/{id}` 不校验归属，可看任意同学单题作答（含正确答案） |

### P1 功能缺陷

| 编号 | 问题 |
|------|------|
| D-004 | 已软删学科仍出现在建题/建卷的学科下拉（`allSubject` SQL 漏 `deleted=0` 条件） |
| D-005 | 题目分值允许负数和 0，未做非负校验，客观题答对会被判负分 |
| D-006 | 已结束时段试卷，学生仍可调 `select/{id}` 进入（接口层不校验 `limitDateTime`） |
| D-007 | 未开始时段试卷，学生仍可调 `select/{id}` 进入 |
| D-008 | 已结束时段试卷，学生仍可正常交卷生成成绩（select 和 answerSubmit 都不校验时间窗） |

### P2 功能缺陷

| 编号 | 问题 |
|------|------|
| D-009 | 学科名称重复未做唯一校验 |
| D-010 | 非法题型 `questionType=999` 静默入库，后端零枚举校验 |
| D-011 | 编辑不存在的学科 id（999999）返回成功，但库里无此记录 |
| D-012 | 同一题目可重复加入试卷未去重，总分被重复累加 |
| D-013 | 建议考试时长负数/0 不拦截，仅非整数才被类型校验拒绝 |
| D-014 | 学生自评分数未校验上限，可给超过题目满分 10 倍的分数 |
| D-015 | 学生自评分数未校验下限，可给负数，学生总成绩直接为负 |

### P3 / 观察项

- **D-016**（P3）：学生调 `message/read/{id}` 不校验归属，可把别人消息标记已读（仅改状态，看不到内容）
- **O-001**：逻辑删除题目后试卷仍可作答；物理删除才报 500
- **O-002**：允许白卷（零作答）交卷得 0 分，产品策略待确认
- **BD-001**：被题目引用的学科仍可软删——这是"留档"设计，不是 bug

## 约定

- 所有测试数据命名前缀 `自动化_`，便于识别和清理
- 临时学生用户名前缀 `autotest_stu_`
- 用例编号格式 `XXX-001`（如 `LOGIN-001`、`PERM-003`），写在 docstring 首行，自动打到 Allure
- `xfail` 标记的用例：P0/P1 用 `strict=True`（修复后变红提醒），P2 用 `strict=False`
