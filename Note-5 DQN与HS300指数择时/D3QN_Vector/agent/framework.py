import random
from collections import deque
import numpy as np
import tensorflow as tf
import sonnet as snt
from agent.forward import Forward
from config import *


_EPSILON = 1e-6  # avoid nan


class Framework(object):
    def __init__(self):
        # placeholder
        self.inputs = tf.placeholder(tf.float32, INPUT_SHAPE, 'input')
        self.actions = tf.placeholder(tf.int32, [None, UNIVERSE_SIZE], 'action')
        self.rewards = tf.placeholder(tf.float32, [None], 'reward')
        self.targets = tf.placeholder(tf.float32, [None], 'targets')
        self.value_net = Forward("value")
        self.target_net = Forward("target")

        # Q value eval
        self.value_eval = snt.BatchApply(self.value_net, 2)(self.inputs)
        self.step_value_eval = tf.squeeze(self.value_eval, axis=0)

        # Q_ target eval
        next_value = tf.stop_gradient(self.value_eval)
        action_next = tf.one_hot(tf.argmax(next_value, axis=2), ACTION_SIZE, axis=2)
        target_eval = snt.BatchApply(self.target_net, 2)(self.inputs)
        target_eval = tf.reduce_sum(target_eval * action_next, axis=2)
        self.target_eval = tf.reduce_mean(target_eval, axis=1)

        # loss function
        action_choice = tf.one_hot(self.actions, ACTION_SIZE, axis=2)
        action_eval = tf.reduce_sum(self.value_eval * action_choice, axis=2)
        # warning
        action_eval = tf.reduce_mean(action_eval, axis=1)
        loss = tf.squared_difference(self.targets, action_eval)
        self._loss = tf.reduce_sum(loss)

        # train op
        trainable_variables = tf.get_collection(
            tf.GraphKeys.TRAINABLE_VARIABLES, 'value')
        grads, _ = tf.clip_by_global_norm(
            tf.gradients(self._loss, trainable_variables), MAX_GRAD_NORM)
        optimizer = tf.contrib.opt.NadamOptimizer()
        self._train_op = optimizer.apply_gradients(
            zip(grads, trainable_variables))

        # update target net params
        eval_net_params = tf.get_collection(tf.GraphKeys.GLOBAL_VARIABLES, "value")
        target_net_params = tf.get_collection(tf.GraphKeys.GLOBAL_VARIABLES, "target")
        self._target_params_swap = \
            [tf.assign(n, q) for n, q in zip(target_net_params, eval_net_params)]

        # cache for experience replay
        self.cache = deque(maxlen=MEMORY_SIZE)

    def get_deterministic_policy(self, sess, inputs):
        value_eval = sess.run(self.step_value_eval, {self.inputs: inputs})
        return np.argmax(value_eval, axis=1)

    def get_stochastic_policy(self, sess, inputs, epsilon=0.9):
        if np.random.uniform() < epsilon:
            return self.get_deterministic_policy(sess, inputs)
        else:
            return np.random.randint(0, ACTION_SIZE, UNIVERSE_SIZE)

    # update target network params
    def update_target_net(self, sess):
        sess.run(self._target_params_swap)

    # update experience replay pool
    def update_cache(self, state, action, reward, next_state, done):
        self.cache.append((state, action, reward, next_state, done))

    # get random sample from experience pool
    def _get_samples(self):
        samples = random.sample(self.cache, BATCH_SIZE)
        state = np.vstack([i[0] for i in samples])
        action = np.squeeze(np.vstack([i[1] for i in samples]))
        reward = np.squeeze(np.vstack([i[2] for i in samples]))
        next_state = np.vstack([i[3] for i in samples])
        done = [i[4] for i in samples]
        return state, action, reward, next_state, done

    # train, update value network params
    def update_value_net(self, sess):
        state, action, reward, next_state, done = self._get_samples()
        mask = np.array(done).astype('float')
        target_eval = sess.run(self.target_eval, {self.inputs: next_state})
        target = mask * reward + (1 - mask) * (reward + GAMMA * target_eval)
        sess.run(self._train_op, {self.inputs: state, self.actions: action, self.targets: target})



