import torch
import pprint
import argparse
import numpy as np
from torch.utils.tensorboard import SummaryWriter

from tianshou.policy import A2CPolicy
from tianshou.env import SubprocVectorEnv
from tianshou.trainer import onpolicy_trainer
from tianshou.data import Collector, ReplayBuffer
from tianshou.env.atari import create_atari_environment

from .discrete_net import MLP, Actor, Critic


def get_args():
    parser = argparse.ArgumentParser()
    parser.add_argument('--task', type=str, default='Pong')
    parser.add_argument('--seed', type=int, default=1626)
    parser.add_argument('--buffer-size', type=int, default=20000)
    parser.add_argument('--lr', type=float, default=3e-4)
    parser.add_argument('--gamma', type=float, default=0.9)
    parser.add_argument('--epoch', type=int, default=100)
    parser.add_argument('--step-per-epoch', type=int, default=1000)
    parser.add_argument('--collect-per-step', type=int, default=100)
    parser.add_argument('--repeat-per-collect', type=int, default=1)
    parser.add_argument('--batch-size', type=int, default=64)
    parser.add_argument('--layer-num', type=int, default=2)
    parser.add_argument('--training-num', type=int, default=8)
    parser.add_argument('--test-num', type=int, default=8)
    parser.add_argument('--logdir', type=str, default='log')
    parser.add_argument('--render', type=float, default=0.)

    parser.add_argument(
        '--device', type=str,
        default='cuda' if torch.cuda.is_available() else 'cpu')
    # a2c special
    parser.add_argument('--vf-coef', type=float, default=0.5)
    parser.add_argument('--ent-coef', type=float, default=0.001)
    parser.add_argument('--max-grad-norm', type=float, default=None)
    parser.add_argument('--max_episode_steps', type=int, default=2000)
    args = parser.parse_known_args()[0]
    return args


def test_a2c(args=get_args()):
    env = create_atari_environment(
        args.task, max_episode_steps=args.max_episode_steps)
    args.state_shape = env.observation_space.shape or env.observation_space.n
    args.action_shape = env.env.action_space.shape or env.env.action_space.n
    # train_envs = gym.make(args.task)
    train_envs = SubprocVectorEnv(
        [lambda: create_atari_environment(
            args.task, max_episode_steps=args.max_episode_steps)
            for _ in range(args.training_num)])
    # test_envs = gym.make(args.task)
    test_envs = SubprocVectorEnv(
        [lambda: create_atari_environment(
            args.task, max_episode_steps=args.max_episode_steps)
            for _ in range(args.test_num)])
    # seed
    np.random.seed(args.seed)
    torch.manual_seed(args.seed)
    train_envs.seed(args.seed)
    test_envs.seed(args.seed)
    # model
    net = MLP(args.layer_num, args.state_shape, device=args.device)
    actor = Actor(net, args.action_shape).to(args.device)
    critic = Critic(net).to(args.device)
    optim = torch.optim.Adam(list(
        actor.parameters()) + list(critic.parameters()), lr=args.lr)
    dist = torch.distributions.Categorical
    policy = A2CPolicy(
        actor, critic, optim, dist, args.gamma, vf_coef=args.vf_coef,
        ent_coef=args.ent_coef, max_grad_norm=args.max_grad_norm)
    # collector
    train_collector = Collector(
        policy, train_envs, ReplayBuffer(args.buffer_size))
    test_collector = Collector(policy, test_envs)
    # log
    writer = SummaryWriter(args.logdir + '/' + 'a2c')

    def stop_fn(x):
        if env.env.spec.reward_threshold:
            return x >= env.spec.reward_threshold
        else:
            return False

    # trainer
    result = onpolicy_trainer(
        policy, train_collector, test_collector, args.epoch,
        args.step_per_epoch, args.collect_per_step, args.repeat_per_collect,
        args.test_num, args.batch_size, stop_fn=stop_fn, writer=writer,
        task=args.task)
    train_collector.close()
    test_collector.close()
    if __name__ == '__main__':
        pprint.pprint(result)
        # Let's watch its performance!
        env = create_atari_environment(args.task)
        collector = Collector(policy, env)
        result = collector.collect(n_episode=1, render=args.render)
        print(f'Final reward: {result["rew"]}, length: {result["len"]}')
        collector.close()


if __name__ == '__main__':
    test_a2c()
