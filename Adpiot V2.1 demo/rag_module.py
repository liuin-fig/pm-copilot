"""
AdPilot V2.1 MVP - 本地向量数据库与 RAG 检索模块
使用 ChromaDB 作为本地轻量化向量存储
使用阿里 DashScope Embedding 模型进行向量嵌入
"""

import os
from langchain_community.embeddings import DashScopeEmbeddings
from langchain_community.vectorstores import Chroma
from langchain_core.documents import Document
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

class AdPilotRAG:
    def __init__(self, db_name="adpilot_golden_cases"):
        """
        初始化 RAG 模块

        Args:
            db_name: 数据库名称
        """
        self.db_name = db_name
        self.embeddings = DashScopeEmbeddings(
            dashscope_api_key=os.getenv("DASHSCOPE_API_KEY"),
            model="text-embedding-v1"
        )
        self.vectorstore = None
        self._init_vectorstore()

    def _init_vectorstore(self):
        """
        初始化本地向量数据库
        """
        # 创建或加载 ChromaDB 实例
        self.vectorstore = Chroma(
            collection_name=self.db_name,
            embedding_function=self.embeddings,
            persist_directory="./chromadb"
        )
        print(f"✓ 成功初始化向量数据库: {self.db_name}")

    def insert_golden_case(self, text, metadata):
        """
        插入 Golden Case 到向量数据库

        Args:
            text: 150字话术正文
            metadata: 元数据字典，必须包含 industry, budget, goal, pain_point

        Returns:
            bool: 插入是否成功
        """
        # 验证 metadata 包含必要字段
        required_fields = ["industry", "budget", "goal", "pain_point"]
        for field in required_fields:
            if field not in metadata:
                print(f"✗ 错误: metadata 缺少必需字段 {field}")
                return False

        # 创建文档对象
        document = Document(
            page_content=text,
            metadata=metadata
        )

        # 插入到向量数据库
        try:
            self.vectorstore.add_documents([document])
            # 持久化存储
            self.vectorstore.persist()
            print(f"✓ 成功插入 Golden Case: {metadata['industry']} - {metadata['goal']}")
            return True
        except Exception as e:
            print(f"✗ 插入失败: {str(e)}")
            return False

    def retrieve_best_scripts(self, query, metadata_filter):
        """
        精准 RAG 检索

        Args:
            query: 用户查询输入
            metadata_filter: 元数据过滤条件，如 {"industry": "美妆", "goal": "首次破冰"}

        Returns:
            list: 检索到的 Top-3 结果
        """
        print(f"🔍 执行检索: 查询='{query}', 过滤条件={metadata_filter}")

        try:
            # 执行混合检索：先硬过滤，再向量相似度
            results = self.vectorstore.similarity_search(
                query=query,
                k=3,
                filter=metadata_filter
            )

            # 格式化结果
            formatted_results = []
            for i, result in enumerate(results, 1):
                formatted_results.append({
                    "rank": i,
                    "text": result.page_content,
                    "metadata": result.metadata,
                    "score": "N/A"  # ChromaDB 在 similarity_search 中不返回分数
                })

            return formatted_results
        except Exception as e:
            print(f"✗ 检索失败: {str(e)}")
            return []

# 测试用例
def test_rag_module():
    """
    测试 RAG 模块功能
    """
    print("\n=== 开始测试 RAG 模块 ===")

    # 初始化 RAG 模块
    rag = AdPilotRAG()

    # Mock 数据 1
    text1 = "您好，了解到您在美妆行业刚起步，针对成本顾虑，建议先以3000元小预算测试，聚焦精准人群，本周内可看到初步效果。"
    metadata1 = {
        "industry": "美妆",
        "budget": "低预算",
        "goal": "首次破冰",
        "pain_point": "嫌贵"
    }

    # Mock 数据 2
    text2 = "您好，作为美妆行业的资深从业者，针对您担心效果的问题，我们可以先进行小规模测试，根据数据反馈持续优化投放策略，确保每一分钱都花在刀刃上。"
    metadata2 = {
        "industry": "美妆",
        "budget": "中预算",
        "goal": "首次破冰",
        "pain_point": "怕没效果"
    }

    # 插入测试数据
    rag.insert_golden_case(text1, metadata1)
    rag.insert_golden_case(text2, metadata2)

    # 测试检索：过滤条件为美妆行业 + 首次破冰
    query = "推荐一个适合新客户的话术"
    metadata_filter = {"industry": "美妆", "goal": "首次破冰"}

    results = rag.retrieve_best_scripts(query, metadata_filter)

    print("\n=== 检索结果 ===")
    if results:
        for result in results:
            print(f"\nRank {result['rank']}:")
            print(f"Text: {result['text']}")
            print(f"Metadata: {result['metadata']}")
    else:
        print("没有找到匹配的结果")

    print("\n=== 测试完成 ===")

if __name__ == "__main__":
    test_rag_module()
