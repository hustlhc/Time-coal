import argparse
import os
import torch
import torch.backends
from exp.exp_long_term_forecasting import Exp_Long_Term_Forecast
#from exp.exp_imputation import Exp_Imputation
#from exp.exp_short_term_forecasting import Exp_Short_Term_Forecast
#from exp.exp_anomaly_detection import Exp_Anomaly_Detection
#from exp.exp_classification import Exp_Classification
from utils.print_args import print_args
import random
import numpy as np

if __name__ == '__main__':
    fix_seed = 2021
    random.seed(fix_seed)
    torch.manual_seed(fix_seed)
    np.random.seed(fix_seed)

    parser = argparse.ArgumentParser(description='TimesNet')

    # basic config
    parser.add_argument('--delt',type=int,default=1)
    parser.add_argument('--task_name', type=str, required=True, default='long_term_forecast',
                        help='task name, options:[long_term_forecast, short_term_forecast, imputation, classification, anomaly_detection]')
    parser.add_argument('--is_training', type=int, required=True, default=1, help='status')
    parser.add_argument('--model_id', type=str, required=True, default='test', help='model id')
    parser.add_argument('--model', type=str, required=True, default='Autoformer',
                        help='model name, options: [Autoformer, Transformer, TimesNet]')
    parser.add_argument('--do_predict', type=int, default=0, help='是否只做推理')
    parser.add_argument('--is_testing', type=int, default=1, help='是否测试')
    parser.add_argument('--is_testing4predict', type=int, default=0, help='是否用测试方式推理')
    parser.add_argument('--is_full_training', type=int, default=1, help='是否全量')
    parser.add_argument('--do_finetune',type=int, default=0, help='是否微调')

    parser.add_argument('--use_weighted_loss', type=int, default=0,
                    help='1: enable weighted loss, 0: disable weighted loss')
    parser.add_argument('--loss_weight_mode', type=str, default='linear', choices=['linear', 'exp', 'piecewise'],
                    help='weighting strategy for loss')
    parser.add_argument('--loss_weight_alpha', type=float, default=0.5, help='weight at the beginning (for linear/piecewise)')
    parser.add_argument('--loss_weight_split', type=float, default=0.5, help='split point (for piecewise)')
    parser.add_argument('--use_short_horizon_weight_loss', type=int, default=0,
                    help='1: up-weight the first N forecast steps in MSE loss')
    parser.add_argument('--short_horizon_weight_days', type=int, default=30,
                    help='number of early forecast steps to up-weight')
    parser.add_argument('--short_horizon_weight', type=float, default=2.0,
                    help='loss weight for the early forecast steps')
    parser.add_argument('--short_horizon_weight_normalize', type=int, default=1,
                    help='1: normalize horizon weights so average loss scale stays stable')
    parser.add_argument('--forecast_loss', type=str, default='mse',
                    choices=['mse', 'huber', 'mae'],
                    help='point forecast loss used by long-term forecasting')
    parser.add_argument('--huber_delta', type=float, default=1.0,
                    help='Huber transition point in scaled target units')

    parser.add_argument('--use_acc_loss', type=int, default=0,
                    help='1: enable acc loss, 0: disable acc loss')
    parser.add_argument('--acc_loss_weight', type=float, default=0.5, help='acc loss weight')
    parser.add_argument('--use_short_trend_loss', type=int, default=0,
                    help='1: enable short-horizon trend direction loss')
    parser.add_argument('--short_trend_loss_weight', type=float, default=0.5,
                    help='short trend loss weight')
    parser.add_argument('--short_trend_month_len', type=int, default=20,
                    help='number of steps per short trend segment')
    parser.add_argument('--short_trend_month_weights', type=str, default='0.6,0.25,0.15',
                    help='comma-separated weights for short trend segments')
    parser.add_argument('--short_trend_max_segments', type=int, default=3,
                    help='maximum number of trend segments; 6 covers a 120-step forecast with 20-step segments')
    parser.add_argument('--use_month_onehot', type=int, default=0,
                    help='1: append 12 month one-hot features to timeF marks')
    parser.add_argument('--use_seasonal_loss', type=int, default=0,
                    help='1: enable month-based seasonal loss weights')
    parser.add_argument('--seasonal_loss_months', type=str, default='9,11,12',
                    help='comma-separated months to up-weight, e.g. 1,4,6,9,11,12')
    parser.add_argument('--seasonal_loss_weight', type=float, default=1.3,
                    help='loss weight for selected seasonal months')
    parser.add_argument('--seasonal_loss_normalize', type=int, default=1,
                        help='1: normalize seasonal weights by batch mean')
    parser.add_argument('--use_sync_loss', type=int, default=0,
                        help='1: add multi-target trend synchronization loss during training')
    parser.add_argument('--sync_loss_weight', type=float, default=0.05,
                        help='weight for multi-target trend synchronization loss')
    parser.add_argument('--sync_infer_targets', type=int, default=0,
                        help='1: synchronize multi-target curves inside test/predict outputs')
    parser.add_argument('--sync_infer_strength', type=float, default=0.6,
                        help='inference synchronization strength, 0 keeps raw output, 1 fully shares relative trend')
    parser.add_argument('--sync_anchor_mode', type=str, default='all_mean',
                        choices=['all_mean', 'domestic_mean', 'imported_mean'],
                        help='trend synchronization anchor')
    parser.add_argument('--sync_align_targets', type=str, default='all',
                        choices=['all', 'domestic', 'imported'],
                        help='target curves adjusted by trend synchronization')
    parser.add_argument('--trans',type=int,default=0)
    parser.add_argument('--last_ten',type=int,default=0)



    # data loader
    parser.add_argument('--data', type=str, required=True, default='ETTh1', help='dataset type')
    parser.add_argument('--root_path', type=str, default='./data/ETT/', help='root path of the data file')
    parser.add_argument('--data_path', type=str, default='ETTh1.csv', help='data file')
    parser.add_argument('--features', type=str, default='M',
                        help='forecasting task, options:[M, S, MS]; M:multivariate predict multivariate, S:univariate predict univariate, MS:multivariate predict univariate')
    parser.add_argument('--target_features', type=int, default=3,
                        help='forecasting task target feature num (OT num)')
    parser.add_argument('--target', type=str, default='OT', help='target feature in S or MS task')
    parser.add_argument('--freq', type=str, default='h',
                        help='freq for time features encoding, options:[s:secondly, t:minutely, h:hourly, d:daily, b:business days, w:weekly, m:monthly], you can also use more detailed freq like 15min or 3h')
    parser.add_argument('--checkpoints', type=str, default='./checkpoints/', help='location of model checkpoints')

    # forecasting task
    parser.add_argument('--seq_len', type=int, default=96, help='input sequence length')
    parser.add_argument('--label_len', type=int, default=48, help='start token length')
    parser.add_argument('--pred_len', type=int, default=96, help='prediction sequence length')
    parser.add_argument('--eval_pred_len', type=int, default=0,
                        help='validation/test horizon for early stopping; 0 means pred_len')
    parser.add_argument('--seasonal_patterns', type=str, default='Monthly', help='subset for M4')
    parser.add_argument('--inverse', action='store_true', help='inverse output data', default=True)
    parser.add_argument('--targetnum', type=int, default=1)

    # inputation task
    parser.add_argument('--mask_rate', type=float, default=0.25, help='mask ratio')

    # anomaly detection task
    parser.add_argument('--anomaly_ratio', type=float, default=0.25, help='prior anomaly ratio (%%)')

    # model define
    parser.add_argument('--expand', type=int, default=2, help='expansion factor for Mamba')
    parser.add_argument('--d_conv', type=int, default=4, help='conv kernel size for Mamba')
    parser.add_argument('--top_k', type=int, default=5, help='for TimesBlock')
    parser.add_argument('--num_kernels', type=int, default=6, help='for Inception')
    parser.add_argument('--enc_in', type=int, default=7, help='encoder input size')
    parser.add_argument('--dec_in', type=int, default=7, help='decoder input size')
    parser.add_argument('--c_out', type=int, default=7, help='output size')
    parser.add_argument('--d_model', type=int, default=512, help='dimension of model')
    parser.add_argument('--n_heads', type=int, default=8, help='num of heads')
    parser.add_argument('--e_layers', type=int, default=2, help='num of encoder layers')
    parser.add_argument('--d_layers', type=int, default=1, help='num of decoder layers')
    parser.add_argument('--d_ff', type=int, default=2048, help='dimension of fcn')
    parser.add_argument('--moving_avg', type=int, default=25, help='window size of moving average')
    parser.add_argument('--factor', type=int, default=1, help='attn factor')
    parser.add_argument('--distil', action='store_false',
                        help='whether to use distilling in encoder, using this argument means not using distilling',
                        default=True)
    parser.add_argument('--dropout', type=float, default=0.1, help='dropout')
    parser.add_argument('--embed', type=str, default='timeF',
                        help='time features encoding, options:[timeF, fixed, learned]')
    parser.add_argument('--activation', type=str, default='gelu', help='activation')
    parser.add_argument('--channel_independence', type=int, default=1,
                        help='0: channel dependence 1: channel independence for FreTS model')
    parser.add_argument('--decomp_method', type=str, default='moving_avg',
                        help='method of series decompsition, only support moving_avg or dft_decomp')
    parser.add_argument('--use_norm', type=int, default=1, help='whether to use normalize; True 1 False 0')
    parser.add_argument('--down_sampling_layers', type=int, default=0, help='num of down sampling layers')
    parser.add_argument('--down_sampling_window', type=int, default=1, help='down sampling window size')
    parser.add_argument('--down_sampling_method', type=str, default=None,
                        help='down sampling method, only support avg, max, conv')
    parser.add_argument('--seg_len', type=int, default=96,
                        help='the length of segmen-wise iteration of SegRNN')

    # optimization
    parser.add_argument('--num_workers', type=int, default=10, help='data loader num workers')
    parser.add_argument('--itr', type=int, default=1, help='experiments times')
    parser.add_argument('--train_epochs', type=int, default=10, help='train epochs')
    parser.add_argument('--batch_size', type=int, default=32, help='batch size of train input data')
    parser.add_argument('--patience', type=int, default=3, help='early stopping patience')
    parser.add_argument('--learning_rate', type=float, default=0.0001, help='optimizer learning rate')
    parser.add_argument('--des', type=str, default='test', help='exp description')
    parser.add_argument('--loss', type=str, default='MSE', help='loss function')
    parser.add_argument('--lradj', type=str, default='type1', help='adjust learning rate')
    parser.add_argument('--use_amp', action='store_true', help='use automatic mixed precision training', default=False)

    # GPU
    parser.add_argument('--use_gpu', type=bool, default=True, help='use gpu')
    parser.add_argument('--gpu', type=int, default=0, help='gpu')
    parser.add_argument('--gpu_type', type=str, default='cuda', help='gpu type: cuda, mps, xpu')
    parser.add_argument('--use_multi_gpu', action='store_true', help='use multiple gpus', default=False)
    parser.add_argument('--devices', type=str, default='0,1,2,3', help='device ids of multile gpus')

    # de-stationary projector params
    parser.add_argument('--p_hidden_dims', type=int, nargs='+', default=[128, 128],
                        help='hidden layer dimensions of projector (List)')
    parser.add_argument('--p_hidden_layers', type=int, default=2, help='number of hidden layers in projector')

    # metrics (dtw)
    parser.add_argument('--use_dtw', type=bool, default=False,
                        help='the controller of using dtw metric (dtw is time consuming, not suggested unless necessary)')

    # Augmentation
    parser.add_argument('--augmentation_ratio', type=int, default=0, help="How many times to augment")
    parser.add_argument('--seed', type=int, default=2, help="Randomization seed")
    parser.add_argument('--jitter', default=False, action="store_true", help="Jitter preset augmentation")
    parser.add_argument('--scaling', default=False, action="store_true", help="Scaling preset augmentation")
    parser.add_argument('--permutation', default=False, action="store_true",
                        help="Equal Length Permutation preset augmentation")
    parser.add_argument('--randompermutation', default=False, action="store_true",
                        help="Random Length Permutation preset augmentation")
    parser.add_argument('--magwarp', default=False, action="store_true", help="Magnitude warp preset augmentation")
    parser.add_argument('--timewarp', default=False, action="store_true", help="Time warp preset augmentation")
    parser.add_argument('--windowslice', default=False, action="store_true", help="Window slice preset augmentation")
    parser.add_argument('--windowwarp', default=False, action="store_true", help="Window warp preset augmentation")
    parser.add_argument('--rotation', default=False, action="store_true", help="Rotation preset augmentation")
    parser.add_argument('--spawner', default=False, action="store_true", help="SPAWNER preset augmentation")
    parser.add_argument('--dtwwarp', default=False, action="store_true", help="DTW warp preset augmentation")
    parser.add_argument('--shapedtwwarp', default=False, action="store_true", help="Shape DTW warp preset augmentation")
    parser.add_argument('--wdba', default=False, action="store_true", help="Weighted DBA preset augmentation")
    parser.add_argument('--discdtw', default=False, action="store_true",
                        help="Discrimitive DTW warp preset augmentation")
    parser.add_argument('--discsdtw', default=False, action="store_true",
                        help="Discrimitive shapeDTW warp preset augmentation")
    parser.add_argument('--extra_tag', type=str, default="", help="Anything extra")

    # TimeXer
    parser.add_argument('--patch_len', type=int, default=16, help='patch length')

    # 添加结果保存路径参数
    parser.add_argument('--csv_path', type=str, default='./pre_result/coal_3800_result.csv', help='full path to save results')

    args = parser.parse_args()

    if args.embed == 'timeF':
        from utils.timefeatures import time_features_from_frequency_str
        args.time_feature_dim = len(time_features_from_frequency_str(args.freq))
        if args.use_month_onehot:
            args.time_feature_dim += 12
    else:
        args.time_feature_dim = None

    # 确保结果目录存在
    if args.csv_path:
        os.makedirs(os.path.dirname(args.csv_path), exist_ok=True)

    # 使用 device_helper 统一处理设备选择
    from utils.device_helper import get_device, empty_cache
    args.device = get_device(args.use_gpu, args.gpu_type, args.gpu, args.devices, args.use_multi_gpu)

    if args.use_gpu and args.use_multi_gpu:
        args.devices = args.devices.replace(' ', '')
        device_ids = args.devices.split(',')
        args.device_ids = [int(id_) for id_ in device_ids]
        args.gpu = args.device_ids[0]

    print('Args in experiment:')
    print_args(args)

    if args.task_name == 'long_term_forecast':
        Exp = Exp_Long_Term_Forecast
    '''
    elif args.task_name == 'short_term_forecast':
        Exp = Exp_Short_Term_Forecast
    elif args.task_name == 'imputation':
        Exp = Exp_Imputation
    #lif args.task_name == 'anomaly_detection':
        Exp = Exp_Anomaly_Detection
    elif args.task_name == 'classification':
        Exp = Exp_Classification
    else:
        Exp = Exp_Long_Term_Forecast
   '''
   
    if args.do_finetune:
        exp = Exp(args)
        ii = 0
        setting = '{}_{}_{}_{}_ft{}_sl{}_ll{}_pl{}_dm{}_nh{}_el{}_dl{}_df{}_expand{}_dc{}_fc{}_eb{}_dt{}_{}_{}'.format(
            args.task_name,
            args.model_id,
            args.model,
            args.data,
            args.features,
            args.seq_len,
            args.label_len,
            args.pred_len,
            args.d_model,
            args.n_heads,
            args.e_layers,
            args.d_layers,
            args.d_ff,
            args.expand,
            args.d_conv,
            args.factor,
            args.embed,
            args.distil,
            args.des, ii)

        print('>>>>>>>finetune : {}<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<'.format(setting))
        exp.finetune(setting)   
        empty_cache(args.device.type)
        exit(0)
   
    if args.do_predict:
        exp = Exp(args)
        ii = 0
        setting = '{}_{}_{}_{}_ft{}_sl{}_ll{}_pl{}_dm{}_nh{}_el{}_dl{}_df{}_expand{}_dc{}_fc{}_eb{}_dt{}_{}_{}'.format(
            args.task_name,
            args.model_id,
            args.model,
            args.data,
            args.features,
            args.seq_len,
            args.label_len,
            args.pred_len,
            args.d_model,
            args.n_heads,
            args.e_layers,
            args.d_layers,
            args.d_ff,
            args.expand,
            args.d_conv,
            args.factor,
            args.embed,
            args.distil,
            args.des, ii)

        print('>>>>>>>predicting : {}<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<'.format(setting))
        exp.predict(setting)   # 🔹 这里调用你要新增的 predict 方法
        empty_cache(args.device.type)
        exit(0)

   
   
    if args.is_training:
        for ii in range(args.itr):
            # setting record of experiments
            exp = Exp(args)  # set experiments
            setting = '{}_{}_{}_{}_ft{}_sl{}_ll{}_pl{}_dm{}_nh{}_el{}_dl{}_df{}_expand{}_dc{}_fc{}_eb{}_dt{}_{}_{}'.format(
                args.task_name,
                args.model_id,
                args.model,
                args.data,
                args.features,
                args.seq_len,
                args.label_len,
                args.pred_len,
                args.d_model,
                args.n_heads,
                args.e_layers,
                args.d_layers,
                args.d_ff,
                args.expand,
                args.d_conv,
                args.factor,
                args.embed,
                args.distil,
                args.des, ii)

            print('>>>>>>>start training : {}>>>>>>>>>>>>>>>>>>>>>>>>>>'.format(setting))
            exp.train(setting)
            if args.is_testing:     
                print('>>>>>>>testing : {}<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<'.format(setting))
                exp.test(setting)
            empty_cache(args.device.type)
    else:
        exp = Exp(args)  # set experiments
        ii = 0
        setting = '{}_{}_{}_{}_ft{}_sl{}_ll{}_pl{}_dm{}_nh{}_el{}_dl{}_df{}_expand{}_dc{}_fc{}_eb{}_dt{}_{}_{}'.format(
            args.task_name,
            args.model_id,
            args.model,
            args.data,
            args.features,
            args.seq_len,
            args.label_len,
            args.pred_len,
            args.d_model,
            args.n_heads,
            args.e_layers,
            args.d_layers,
            args.d_ff,
            args.expand,
            args.d_conv,
            args.factor,
            args.embed,
            args.distil,
            args.des, ii)

        print('>>>>>>>testing : {}<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<'.format(setting))
        exp.test(setting, test=1)
        empty_cache(args.device.type)
