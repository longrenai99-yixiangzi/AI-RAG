"""A visible scope hint, never a rewrite of the user's question or a coverage verdict."""
import re


def personnel_count_query(question):
    return bool(re.search(r'多少(?:个)?[人名位]|几(?:个)?[人名位]|人数|人员配置数量|(?:团队|岗位|人员).{0,5}(?:总数|数量)',re.sub(r'《[^》]+》','',question)))


def question_scope(question):
    if not personnel_count_query(question):return None
    leader=bool(re.search(r'牵头|统筹|负责人|哪个岗位|谁负责',question))
    team=bool(re.search(r'团队|全员|总人数|总配置人数|全部岗位|所有人员',question))
    if leader and team:return {'kind':'ROLE_AND_TEAM_COUNTS','inferred':True,'label':'本题同时涉及负责人岗位与团队人数，两者需分别核对。'}
    if not leader and (re.search(r'项目管理人员|项目部管理人员',question) or re.search(r'(?:组织架构表|组织结构表).*(?:合计|总|一共)',question)):
        return {'kind':'PROJECT_ORGANIZATION_COUNT','inferred':True,'label':'本题按项目组织表的人员合计核对，不等于仅设计岗位的团队人数。'}
    if re.search(r'阶段',question) and re.search(r'驻场|岗位|人员配置',question) and not re.search(r'团队|全员|全部岗位|所有人员',question):
        return {'kind':'PHASE_POSITION_COUNT','inferred':True,'label':'本题按指定阶段和岗位的人员配置核对，不能用其他阶段或团队合计替代。'}
    if team:return {'kind':'TEAM_COUNT','inferred':True,'label':'本题询问团队人数，不能用一个负责人岗位的人数代替。'}
    if leader or re.search(r'(?:技术|设计|商务|建造|安全|质量)总监|项目经理|设计经理',question):return {'kind':'LEAD_ROLE_COUNT','inferred':True,'label':'本次按牵头岗位及该岗位人数理解，不据此推算团队总人数。'}
    return {'kind':'UNSPECIFIED_COUNT','inferred':True,'label':'人数对象尚不明确，岗位人数与团队总人数需区分。'}
