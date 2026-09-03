import pandas as pd
import numpy as np
import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import DataLoader, TensorDataset
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_squared_error, mean_absolute_error, r2_score
from sklearn.preprocessing import StandardScaler
import matplotlib.pyplot as plt

# 设置随机种子保证可重复性
torch.manual_seed(42)
np.random.seed(42)

class LinearRegressionModel(nn.Module):
    def __init__(self, input_dim, hidden_dims=[64, 32], dropout_rate=0.2):
        """
        基于线性层的回归模型
        
        Parameters:
        input_dim: 输入特征维度
        hidden_dims: 隐藏层维度列表
        dropout_rate: Dropout率
        """
        super(LinearRegressionModel, self).__init__()
        
        layers = []
        prev_dim = input_dim
        
        # 构建隐藏层
        for hidden_dim in hidden_dims:
            layers.extend([
                nn.Linear(prev_dim, hidden_dim),
                nn.BatchNorm1d(hidden_dim),
                nn.ReLU(),
                nn.Dropout(dropout_rate)
            ])
            prev_dim = hidden_dim
        
        # 输出层
        layers.append(nn.Linear(prev_dim, 1))
        
        self.model = nn.Sequential(*layers)
        
    def forward(self, x):
        return self.model(x).squeeze(-1)

class LinearImputer:
    def __init__(self, hidden_dims=[64, 32], dropout_rate=0.2,
                 batch_size=32, learning_rate=0.001,
                 num_epochs=200, patience=20, weight_decay=1e-5):
        """
        初始化线性网络缺失值补全器
        """
        self.model = None
        self.hidden_dims = hidden_dims
        self.dropout_rate = dropout_rate
        self.batch_size = batch_size
        self.learning_rate = learning_rate
        self.num_epochs = num_epochs
        self.patience = patience
        self.weight_decay = weight_decay
        self.num_features = None
        
        self.device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
        
        # 归一化器
        self.feature_scaler = StandardScaler()
        self.target_scaler = StandardScaler()
        
        print(f"使用设备: {self.device}")
    
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
        
        print(f"特征数量: {self.num_features}")
        
        return train_data, infer_data
    
    def prepare_dataloader(self, train_data):
        """
        准备数据加载器（包含数据归一化）
        """
        # 移除目标列有缺失值的样本
        target_col = train_data.iloc[:, -1]
        if target_col.isna().any():
            print("警告: 训练数据的目标列包含缺失值，这些样本将被移除")
            train_data = train_data.dropna(subset=[train_data.columns[-1]])
        
        # 分离特征和目标
        X = train_data.iloc[:, :-1].values.astype(np.float32)  # 特征列
        y = train_data.iloc[:, -1].values.astype(np.float32)   # 目标列
        
        print("数据归一化前统计:")
        print(f"特征 - 均值: {X.mean():.4f}, 标准差: {X.std():.4f}")
        print(f"目标 - 均值: {y.mean():.4f}, 标准差: {y.std():.4f}")
        print(f"目标值范围: [{y.min():.4f}, {y.max():.4f}]")
        
        # 归一化特征数据
        X_normalized = self.feature_scaler.fit_transform(X)
        
        # 归一化目标数据
        y_normalized = self.target_scaler.fit_transform(y.reshape(-1, 1)).flatten()
        
        print("数据归一化后统计:")
        print(f"特征 - 均值: {X_normalized.mean():.4f}, 标准差: {X_normalized.std():.4f}")
        print(f"目标 - 均值: {y_normalized.mean():.4f}, 标准差: {y_normalized.std():.4f}")
        
        # 划分训练集和验证集
        X_train, X_val, y_train, y_val = train_test_split(
            X_normalized, y_normalized, test_size=0.2, random_state=42
        )
        
        # 保存未归一化的验证数据用于最终评估
        _, X_val_original, _, y_val_original = train_test_split(
            X, y, test_size=0.2, random_state=42
        )
        
        print(f"训练集大小: {X_train.shape}")
        print(f"验证集大小: {X_val.shape}")
        
        # 转换为PyTorch张量
        X_train_tensor = torch.FloatTensor(X_train).to(self.device)
        y_train_tensor = torch.FloatTensor(y_train).to(self.device)
        X_val_tensor = torch.FloatTensor(X_val).to(self.device)
        y_val_tensor = torch.FloatTensor(y_val).to(self.device)
        
        # 创建数据加载器
        train_dataset = TensorDataset(X_train_tensor, y_train_tensor)
        val_dataset = TensorDataset(X_val_tensor, y_val_tensor)
        
        train_loader = DataLoader(train_dataset, batch_size=self.batch_size, shuffle=True)
        val_loader = DataLoader(val_dataset, batch_size=self.batch_size, shuffle=False)
        
        return train_loader, val_loader, X_val_original, y_val_original, X_val, y_val
    
    def train_model(self, train_loader, val_loader):
        """
        训练模型
        """
        # 初始化模型
        self.model = LinearRegressionModel(
            input_dim=self.num_features,
            hidden_dims=self.hidden_dims,
            dropout_rate=self.dropout_rate
        ).to(self.device)
        
        # 打印模型结构
        print(f"\n模型结构:")
        print(f"输入维度: {self.num_features}")
        print(f"隐藏层: {self.hidden_dims}")
        total_params = sum(p.numel() for p in self.model.parameters() if p.requires_grad)
        print(f"总参数量: {total_params:,}")
        
        # 定义损失函数和优化器
        criterion = nn.MSELoss()
        optimizer = optim.Adam(self.model.parameters(), 
                              lr=self.learning_rate, 
                              weight_decay=self.weight_decay)
        scheduler = optim.lr_scheduler.ReduceLROnPlateau(optimizer, patience=10, factor=0.5, verbose=True)
        
        best_val_loss = float('inf')
        patience_counter = 0
        train_losses = []
        val_losses = []
        
        print("\n开始训练线性网络模型...")
        
        for epoch in range(self.num_epochs):
            # 训练阶段
            self.model.train()
            train_loss = 0
            for batch_X, batch_y in train_loader:
                optimizer.zero_grad()
                
                outputs = self.model(batch_X)
                loss = criterion(outputs, batch_y)
                
                loss.backward()
                optimizer.step()
                
                train_loss += loss.item()
            
            # 验证阶段
            self.model.eval()
            val_loss = 0
            with torch.no_grad():
                for batch_X, batch_y in val_loader:
                    outputs = self.model(batch_X)
                    loss = criterion(outputs, batch_y)
                    val_loss += loss.item()
            
            avg_train_loss = train_loss / len(train_loader)
            avg_val_loss = val_loss / len(val_loader)
            
            train_losses.append(avg_train_loss)
            val_losses.append(avg_val_loss)
            
            # 学习率调度
            scheduler.step(avg_val_loss)
            
            if epoch % 20 == 0:
                print(f'Epoch [{epoch+1}/{self.num_epochs}], '
                      f'Train Loss: {avg_train_loss:.6f}, Val Loss: {avg_val_loss:.6f}, '
                      f'LR: {optimizer.param_groups[0]["lr"]:.2e}')
            
            # 早停机制
            if avg_val_loss < best_val_loss:
                best_val_loss = avg_val_loss
                patience_counter = 0
                # 保存最佳模型
                torch.save({
                    'model_state_dict': self.model.state_dict(),
                    'optimizer_state_dict': optimizer.state_dict(),
                    'val_loss': best_val_loss,
                    'epoch': epoch
                }, 'best_linear_model.pth')
            else:
                patience_counter += 1
                if patience_counter >= self.patience:
                    print(f'早停于第 {epoch+1} 轮')
                    break
        
        # 加载最佳模型
        checkpoint = torch.load('best_linear_model.pth')
        self.model.load_state_dict(checkpoint['model_state_dict'])
        
        # 绘制损失曲线
        self._plot_loss_curves(train_losses, val_losses)
        
        return best_val_loss
    
    def _plot_loss_curves(self, train_losses, val_losses):
        """绘制损失曲线"""
        plt.figure(figsize=(10, 6))
        plt.plot(train_losses, label='Training Loss')
        plt.plot(val_losses, label='Validation Loss')
        plt.xlabel('Epoch')
        plt.ylabel('Loss (MSE)')
        plt.title('Training and Validation Loss - Linear Network')
        plt.legend()
        plt.grid(True, alpha=0.3)
        plt.savefig('linear_loss_curves.png', dpi=300, bbox_inches='tight')
        plt.close()
    
    def evaluate_model(self, X_val_original, y_val_original, X_val_normalized, y_val_normalized):
        """
        评估模型性能（使用反归一化后的数据）
        """
        if self.model is None:
            raise ValueError("请先训练模型！")
        
        self.model.eval()
        with torch.no_grad():
            X_val_tensor = torch.FloatTensor(X_val_normalized).to(self.device)
            y_pred_normalized = self.model(X_val_tensor).cpu().numpy()
        
        # 反归一化预测结果
        y_pred = self.target_scaler.inverse_transform(y_pred_normalized.reshape(-1, 1)).flatten()
        
        # 计算评估指标（使用原始尺度）
        rmse = np.sqrt(mean_squared_error(y_val_original, y_pred))
        mae = mean_absolute_error(y_val_original, y_pred)
        r2 = r2_score(y_val_original, y_pred)
        
        print("\n=== 模型评估结果 (原始尺度) ===")
        print(f"RMSE (均方根误差): {rmse:.6f}")
        print(f"MAE (平均绝对误差): {mae:.6f}")
        print(f"R² (决定系数): {r2:.6f}")
        
        # 绘制预测结果
        self._plot_predictions(y_val_original, y_pred)
        
        # 绘制残差图
        self._plot_residuals(y_val_original, y_pred)
        
        return rmse, mae, r2
    
    def _plot_predictions(self, y_true, y_pred):
        """绘制预测结果"""
        plt.figure(figsize=(8, 6))
        plt.scatter(y_true, y_pred, alpha=0.6, s=30)
        min_val = min(y_true.min(), y_pred.min())
        max_val = max(y_true.max(), y_pred.max())
        plt.plot([min_val, max_val], [min_val, max_val], 'r--', lw=2, label='完美预测线')
        plt.xlabel('真实值')
        plt.ylabel('预测值')
        plt.title('真实值 vs 预测值 - Linear Network')
        plt.legend()
        plt.grid(True, alpha=0.3)
        plt.savefig('linear_predictions.png', dpi=300, bbox_inches='tight')
        plt.close()
    
    def _plot_residuals(self, y_true, y_pred):
        """绘制残差图"""
        residuals = y_true - y_pred
        plt.figure(figsize=(8, 6))
        plt.scatter(y_pred, residuals, alpha=0.6, s=30)
        plt.axhline(y=0, color='r', linestyle='--', lw=2)
        plt.xlabel('预测值')
        plt.ylabel('残差')
        plt.title('残差图 - Linear Network')
        plt.grid(True, alpha=0.3)
        plt.savefig('linear_residuals.png', dpi=300, bbox_inches='tight')
        plt.close()
    
    def predict_target_column(self, infer_data, output_file=None):
        """
        预测目标列并输出到CSV文件（包含归一化处理）
        """
        if self.model is None:
            raise ValueError("请先训练模型！")
        
        self.model.eval()
        with torch.no_grad():
            # 归一化推理数据
            X_infer_normalized = self.feature_scaler.transform(infer_data.values.astype(np.float32))
            
            # 转换为张量
            X_infer_tensor = torch.FloatTensor(X_infer_normalized).to(self.device)
            
            # 预测（得到归一化的结果）
            predictions_normalized = self.model(X_infer_tensor).cpu().numpy()
            
            # 反归一化到原始尺度
            predictions = self.target_scaler.inverse_transform(predictions_normalized.reshape(-1, 1)).flatten()
        
        print(f"成功为 {len(predictions)} 条推理数据生成预测值")
        
        # 保存到CSV文件
        if output_file:
            np.savetxt(output_file, predictions, delimiter=',', fmt='%.6f')
            print(f"目标列预测值已保存到: {output_file}")
        
        return predictions

def compare_with_baseline(X_train, y_train, X_val, y_val):
    """与简单线性回归基准比较"""
    from sklearn.linear_model import LinearRegression
    from sklearn.metrics import r2_score
    
    # 训练简单线性回归
    lr = LinearRegression()
    lr.fit(X_train, y_train)
    
    # 预测
    y_pred_lr = lr.predict(X_val)
    
    # 计算R²
    r2_lr = r2_score(y_val, y_pred_lr)
    
    print(f"\n=== 基准模型比较 ===")
    print(f"简单线性回归 R²: {r2_lr:.6f}")
    
    return r2_lr

def main():
    # 文件路径
    train_file = 'imputation_gt_new.csv'  # 训练数据文件（包含目标列）
    infer_file = 'imputation_infer_new.csv'  # 推理数据文件（没有目标列）
    output_file = 'linear_predictions.csv'  # 输出文件
    
    # 初始化线性网络补全器
    imputer = LinearImputer(
        hidden_dims=[128, 64, 32],  # 隐藏层维度
        dropout_rate=0.3,           # Dropout率
        batch_size=64,              # 批大小
        learning_rate=0.001,        # 学习率
        num_epochs=300,             # 训练轮数
        patience=25,                # 早停耐心值
        weight_decay=1e-5           # L2正则化
    )
    
    try:
        # 1. 加载数据
        print("正在加载数据...")
        train_data, infer_data = imputer.load_and_prepare_data(train_file, infer_file)
        
        # 2. 准备数据加载器（包含归一化）
        train_loader, val_loader, X_val_original, y_val_original, X_val_normalized, y_val_normalized = imputer.prepare_dataloader(train_data)
        
        # 3. 与基准模型比较
        # 获取未归一化的训练数据用于基准比较
        train_data_clean = train_data.dropna(subset=[train_data.columns[-1]])
        X_train_baseline = train_data_clean.iloc[:, :-1].values
        y_train_baseline = train_data_clean.iloc[:, -1].values
        baseline_r2 = compare_with_baseline(X_train_baseline, y_train_baseline, X_val_original, y_val_original)
        
        # 4. 训练模型
        best_val_loss = imputer.train_model(train_loader, val_loader)
        print(f"最佳验证损失: {best_val_loss:.6f}")
        
        # 5. 评估模型
        rmse, mae, r2 = imputer.evaluate_model(X_val_original, y_val_original, X_val_normalized, y_val_normalized)
        
        # 6. 与基准比较
        print(f"\n=== 性能提升 ===")
        print(f"神经网络 R²: {r2:.6f}")
        print(f"线性回归 R²: {baseline_r2:.6f}")
        improvement = (r2 - baseline_r2) / abs(baseline_r2) * 100 if baseline_r2 != 0 else float('inf')
        print(f"相对提升: {improvement:+.2f}%")
        
        # 7. 进行预测
        if r2 > baseline_r2 or r2 > 0.6:
            print("\n开始预测目标列...")
            predictions = imputer.predict_target_column(infer_data, output_file)
            
            # 显示预测结果统计
            print(f"\n预测值统计 (原始尺度):")
            print(f"最小值: {predictions.min():.6f}")
            print(f"最大值: {predictions.max():.6f}")
            print(f"平均值: {predictions.mean():.6f}")
            print(f"标准差: {predictions.std():.6f}")
            
            print(f"\n前10个预测值:")
            for i, pred in enumerate(predictions[:10]):
                print(f"样本 {i+1}: {pred:.6f}")
                
        else:
            print("模型表现不佳，建议使用简单线性回归")
            
    except Exception as e:
        print(f"处理过程中出现错误: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()