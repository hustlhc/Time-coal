
import pandas as pd
import numpy as np
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_squared_error, mean_absolute_error, r2_score
from sklearn.ensemble import RandomForestRegressor, GradientBoostingRegressor
from sklearn.linear_model import LinearRegression, Ridge, Lasso, ElasticNet
from sklearn.preprocessing import StandardScaler
import xgboost as xgb
from catboost import CatBoostRegressor
import warnings
warnings.filterwarnings('ignore')

class MultiModelImputer:
    def __init__(self, test_size=0.2, random_state=42):
        """
        初始化多模型缺失值补全器
        """
        self.models = {}
        self.feature_indices = None
        self.test_size = test_size
        self.random_state = random_state
        self.num_features = None
        self.target_col_index = -1
        self.selected_model = None
        self.scaler = StandardScaler()
        
        # 初始化所有模型
        self._initialize_models()
    
    def _initialize_models(self):
        """初始化所有回归模型"""
        self.models = {
            '1': {'name': 'XGBoost', 'model': xgb.XGBRegressor(
                max_depth=6, learning_rate=0.1, n_estimators=200,
                subsample=0.8, colsample_bytree=0.8, random_state=self.random_state
            )},
            '3': {'name': 'CatBoost', 'model': CatBoostRegressor(
                depth=6, learning_rate=0.1, iterations=200,
                subsample=0.8, random_state=self.random_state, verbose=False
            )},
            '4': {'name': 'RandomForest', 'model': RandomForestRegressor(
                n_estimators=200, max_depth=6, random_state=self.random_state, n_jobs=-1
            )},
            '5': {'name': 'GradientBoosting', 'model': GradientBoostingRegressor(
                n_estimators=200, max_depth=6, learning_rate=0.1,
                subsample=0.8, random_state=self.random_state
            )},
            '6': {'name': 'LinearRegression', 'model': LinearRegression()},
            '7': {'name': 'Ridge', 'model': Ridge(alpha=1.0, random_state=self.random_state)},
            '8': {'name': 'Lasso', 'model': Lasso(alpha=0.1, random_state=self.random_state)},
            '9': {'name': 'ElasticNet', 'model': ElasticNet(alpha=0.1, l1_ratio=0.5, random_state=self.random_state)}
        }
    
    def load_and_prepare_data(self, train_file, infer_file):
        """
        加载训练数据和推理数据
        """
        # 加载训练数据（包含目标列）
        train_data = pd.read_csv(train_file, header=None)
        print(f"训练数据形状: {train_data.shape}")
        
        # 加载推理数据（没有目标列）
        infer_data = pd.read_csv(infer_file, header=None)
        print(f"推理数据形状: {infer_data.shape}")
        
        # 检查特征数量是否一致
        if train_data.shape[1] - 1 != infer_data.shape[1]:
            raise ValueError(f"特征数量不匹配: 训练数据有{train_data.shape[1]-1}个特征，推理数据有{infer_data.shape[1]}个特征")
        
        # 设置特征数量
        self.num_features = train_data.shape[1] - 1
        self.feature_indices = list(range(self.num_features))
        
        print(f"特征数量: {self.num_features}")
        
        return train_data, infer_data
    
    def train_model(self, train_data, model_key):
        """
        训练指定模型
        """
        if model_key not in self.models:
            raise ValueError(f"无效的模型选择: {model_key}")
        
        model_info = self.models[model_key]
        model_name = model_info['name']
        model = model_info['model']
        
        print(f"\n开始训练 {model_name}...")
        
        # 移除目标列有缺失值的样本
        target_col = train_data.iloc[:, self.target_col_index]
        if target_col.isna().any():
            train_data = train_data.dropna(subset=[train_data.columns[self.target_col_index]])
        
        # 准备特征和目标变量
        X = train_data.iloc[:, self.feature_indices].values
        y = train_data.iloc[:, self.target_col_index].values
        
        # 对线性模型进行特征标准化
        if model_name in ['LinearRegression', 'Ridge', 'Lasso', 'ElasticNet']:
            X = self.scaler.fit_transform(X)
        
        print(f"有效训练数据大小: {X.shape}")
        
        # 划分训练集和测试集
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=self.test_size, random_state=self.random_state
        )
        
        # 训练模型
        model.fit(X_train, y_train)
        self.selected_model = model
        
        # 在测试集上评估
        y_pred = model.predict(X_test)
        
        rmse = np.sqrt(mean_squared_error(y_test, y_pred))
        mae = mean_absolute_error(y_test, y_pred)
        r2 = r2_score(y_test, y_pred)
        
        print(f"\n=== {model_name} 模型评估结果 ===")
        print(f"RMSE (均方根误差): {rmse:.4f}")
        print(f"MAE (平均绝对误差): {mae:.4f}")
        print(f"R² (决定系数): {r2:.4f}")
        
        return rmse, mae, r2
    
    def predict_target_column(self, infer_data, output_file=None):
        """
        预测目标列并输出到CSV文件
        """
        if self.selected_model is None:
            raise ValueError("请先训练模型！")
        
        # 准备推理数据的特征
        X_infer = infer_data.values
        
        # 检查特征数量是否匹配
        if X_infer.shape[1] != self.num_features:
            raise ValueError(f"推理数据特征数量({X_infer.shape[1]})与训练特征数量({self.num_features})不匹配")
        
        # 对线性模型进行特征标准化
        model_name = self._get_model_name(self.selected_model)
        if model_name in ['LinearRegression', 'Ridge', 'Lasso', 'ElasticNet']:
            X_infer = self.scaler.transform(X_infer)
        
        # 预测目标列
        predictions = self.selected_model.predict(X_infer)
        print(f"成功为 {len(predictions)} 条推理数据生成预测值")
        
        # 将预测值转换为数值型
        predictions_numeric = predictions.astype(float)
        
        # 保存到CSV文件
        if output_file:
            # 创建DataFrame并保存
            result_df = pd.DataFrame(predictions_numeric, columns=['predicted_target'])
            result_df.to_csv(output_file, index=False, header=False)
            print(f"目标列预测值已保存到: {output_file}")
        
        return predictions_numeric
    
    def _get_model_name(self, model):
        """获取模型名称"""
        for key, info in self.models.items():
            if info['model'] == model:
                return info['name']
        return "Unknown"
    
    def show_model_options(self):
        """显示模型选项"""
        print("\n可用的模型选项:")
        print("=" * 40)
        for key, info in self.models.items():
            print(f"{key}. {info['name']}")
        print("=" * 40)

def main():
    # 文件路径
    train_file = 'imputation_gt_new.csv'  # 训练数据文件（包含目标列）
    infer_file = 'imputation_infer_new.csv'  # 推理数据文件（没有目标列）
    output_file = 'target_predictions.csv'  # 输出文件（只包含目标列预测值）
    
    # 初始化补全器
    imputer = MultiModelImputer(random_state=42)
    
    try:
        # 1. 加载数据
        print("正在加载数据...")
        train_data, infer_data = imputer.load_and_prepare_data(train_file, infer_file)
        
        # 2. 显示模型选项
        imputer.show_model_options()
        
        # 3. 用户选择模型
        while True:
            choice = input("\n请选择要使用的模型编号 (1-9): ").strip()
            if choice in imputer.models:
                break
            print("无效的选择，请重新输入！")
        
        # 4. 训练模型
        rmse, mae, r2 = imputer.train_model(train_data, choice)
        
        # 5. 如果模型表现良好，进行预测
        if r2 > 0.6:
            print("\n模型表现良好，开始预测目标列...")
            # 预测目标列并保存
            predictions = imputer.predict_target_column(infer_data, output_file)
            
            # 显示部分预测结果
            print(f"\n前10个预测值:")
            for i, pred in enumerate(predictions[:10]):
                print(f"样本 {i+1}: {pred:.6f}")
                
            print(f"\n预测值统计:")
            print(f"最小值: {predictions.min():.6f}")
            print(f"最大值: {predictions.max():.6f}")
            print(f"平均值: {predictions.mean():.6f}")
            print(f"标准差: {predictions.std():.6f}")
            
        else:
            print("模型表现不佳(R² < 0.6)，建议:")
            print("1. 尝试其他模型")
            print("2. 调整模型参数")
            print("3. 检查数据质量")
            
    except FileNotFoundError as e:
        print(f"文件未找到: {e}")
        print("请确保以下文件存在:")
        print(f"- 训练数据: {train_file}")
        print(f"- 推理数据: {infer_file}")
    except Exception as e:
        print(f"处理过程中出现错误: {e}")

if __name__ == "__main__":
    main()